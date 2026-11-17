from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts.validate_release_qualification import EXPECTED_IMAGES, validate


ROOT = Path(__file__).parents[2]
COMMIT = "a" * 40


def _bundle(tmp_path: Path) -> tuple[Path, Path, dict]:
    package = "b" * 64
    images = {}
    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    for index, name in enumerate(sorted(EXPECTED_IMAGES), start=1):
        digest = f"{index:x}" * 64
        reference = (
            f"us-central1-docker.pkg.dev/example-project/cogniflow-images/{name}"
            f"@sha256:{digest}"
        )
        images[name] = {
            "reference": reference,
            "source_commit": COMMIT,
            "model_package_sha256": package,
            "sbom_sha256": "c" * 64,
            "provenance_sha256": "d" * 64,
        }
        (scan_dir / f"{name}.trivy.json").write_text(json.dumps({
            "ArtifactName": reference,
            "Results": [{"Target": name, "Vulnerabilities": []}],
        }))
    payload = {
        "source_commit": COMMIT,
        "authorization": {
            "approved": True,
            "environment": "m10-release-qualification",
            "actor": "github-owner:nhatminh06",
        },
        "model": {
            "approval_status": "approved",
            "approval_commit": COMMIT,
            "artifact_sha256": "e" * 64,
            "dataset_sha256": "f" * 64,
            "package_sha256": package,
        },
        "images": images,
    }
    bundle = tmp_path / "qualification.json"
    bundle.write_text(json.dumps(payload))
    return bundle, scan_dir, payload


def _write(bundle: Path, payload: dict) -> None:
    bundle.write_text(json.dumps(payload))


def test_complete_release_bundle_passes_offline_policy(tmp_path: Path) -> None:
    bundle, scan_dir, _ = _bundle(tmp_path)
    validate(bundle, scan_dir, COMMIT)


@pytest.mark.parametrize("mutation", ["authorization", "commit", "candidate", "digest", "identity"])
def test_release_identity_failures_are_closed(tmp_path: Path, mutation: str) -> None:
    bundle, scan_dir, original = _bundle(tmp_path)
    payload = copy.deepcopy(original)
    if mutation == "authorization":
        payload["authorization"]["approved"] = False
    elif mutation == "commit":
        payload["source_commit"] = "0" * 40
    elif mutation == "candidate":
        payload["model"]["approval_status"] = "candidate"
    elif mutation == "digest":
        payload["images"]["cognitive-load-api"]["reference"] = "repo/image:latest"
    else:
        payload["images"]["cogniflow-kserve"]["model_package_sha256"] = "0" * 64
    _write(bundle, payload)
    with pytest.raises(ValueError):
        validate(bundle, scan_dir, COMMIT)


@pytest.mark.parametrize("failure", ["missing", "malformed", "vulnerable", "wrong-image"])
def test_scanner_reports_fail_closed(tmp_path: Path, failure: str) -> None:
    bundle, scan_dir, payload = _bundle(tmp_path)
    name = "event-consumer"
    report = scan_dir / f"{name}.trivy.json"
    if failure == "missing":
        report.unlink()
    elif failure == "malformed":
        report.write_text("[]")
    elif failure == "wrong-image":
        report.write_text(json.dumps({"ArtifactName": "wrong", "Results": []}))
    else:
        report.write_text(json.dumps({
            "ArtifactName": payload["images"][name]["reference"],
            "Results": [{"Vulnerabilities": [{"Severity": "HIGH"}]}],
        }))
    with pytest.raises(ValueError):
        validate(bundle, scan_dir, COMMIT)


def test_manual_qualification_workflow_has_no_release_authority() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release-qualification.yaml").read_text()
    )
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["qualify-source-only"]
    assert job["environment"] == "m10-release-qualification"
    assert job["permissions"] == {"contents": "read"}
    serialized = json.dumps(workflow)
    for forbidden in (
        "id-token", "packages", "docker push", "kubectl", "terraform apply",
        "google-github-actions", "cosign sign", "helm upgrade",
    ):
        assert forbidden not in serialized


def test_gke_values_keep_external_access_fail_closed() -> None:
    values = yaml.safe_load(
        (ROOT / "helm/cognitive-load-monitor/values.gke.yaml").read_text()
    )
    assert values["ingress"]["enabled"] is False
    assert values["ingress"]["authSecret"] == ""
    assert "ingress-nginx" not in json.dumps(values)
    assert values["serviceAccount"]["name"] == "cogniflow-api"
    assert values["networkPolicy"]["externalIngressEnabled"] is False


def test_runner_pods_use_read_only_roots_and_bounded_writable_paths() -> None:
    documents = [
        item for item in yaml.safe_load_all(
            (ROOT / "deploy/gke/ephemeral-runners.yaml").read_text()
        ) if item
    ]
    pods = [item for item in documents if item["kind"] == "Pod"]
    assert {pod["metadata"]["name"] for pod in pods} == {
        "cogniflow-release", "cogniflow-gke-deploy",
    }
    for pod in pods:
        spec = pod["spec"]
        assert spec["automountServiceAccountToken"] is False
        assert spec["securityContext"] == {
            "runAsNonRoot": True,
            "runAsUser": 1001,
            "runAsGroup": 1001,
            "fsGroup": 1001,
            "fsGroupChangePolicy": "OnRootMismatch",
            "seccompProfile": {"type": "RuntimeDefault"},
        }
        assert not any("hostPath" in volume for volume in spec["volumes"])
        volumes = {volume["name"]: volume["emptyDir"] for volume in spec["volumes"]}
        assert set(volumes) == {"runner-home", "work", "runner-temp", "tool-cache"}
        assert all(volume.get("sizeLimit") for volume in volumes.values())

        init = spec["initContainers"]
        assert len(init) == 1
        assert init[0]["args"] == ["cp -a /home/runner/. /runner/"]
        assert "env" not in init[0]
        for container in [*init, *spec["containers"]]:
            security = container["securityContext"]
            assert security["allowPrivilegeEscalation"] is False
            assert security["readOnlyRootFilesystem"] is True
            assert security["capabilities"] == {"drop": ["ALL"]}
            assert security.get("privileged", False) is False

        runner = spec["containers"][0]
        assert runner["workingDir"] == "/runner"
        mounts = {mount["mountPath"]: mount["name"] for mount in runner["volumeMounts"]}
        assert mounts == {
            "/runner": "runner-home",
            "/runner/_work": "work",
            "/runner/_temp": "runner-temp",
            "/runner/_tool": "tool-cache",
        }
        environment = {item["name"]: item for item in runner["env"]}
        assert environment["HOME"]["value"] == "/runner/home"
        assert environment["RUNNER_TEMP"]["value"] == "/runner/_temp"
        assert environment["RUNNER_TOOL_CACHE"]["value"] == "/runner/_tool"
        assert "secretKeyRef" in environment["RUNNER_TOKEN"]["valueFrom"]


def test_deployment_runner_scaffold_fails_closed_on_unverified_inputs() -> None:
    dockerfile = (ROOT / "deploy/gke/runners/Dockerfile.deploy").read_text()
    checksums = (
        ROOT / "deploy/gke/runners/deploy-inputs.SHA256SUMS.example"
    ).read_text()
    assert "@sha256:" in dockerfile
    assert "sha256sum -c SHA256SUMS" in dockerfile
    assert 'dpkg --print-architecture)\" = amd64' in dockerfile
    assert "USER 1001:1001" in dockerfile
    assert "/usr/bin/docker" in dockerfile
    assert "UNVERIFIED" in checksums
    assert "http://" not in dockerfile
    assert "https://" not in dockerfile


def test_gke_render_has_no_external_route_or_unneeded_gateway_ingress() -> None:
    values = yaml.safe_load(
        (ROOT / "helm/cognitive-load-monitor/values.gke.yaml").read_text()
    )
    assert values["serviceAccount"]["name"] == "cogniflow-api"
    assert values["networkPolicy"]["externalIngressEnabled"] is False
    assert values["ingress"]["enabled"] is False


def test_sec022_stays_out_of_every_cloud_release_path() -> None:
    paths = [
        ROOT / ".github/workflows/release-qualification.yaml",
        ROOT / "infra/terraform/gke",
        ROOT / "deploy/gke",
        ROOT / "helm/cognitive-load-monitor/values.gke.yaml",
    ]
    content = "\n".join(
        item.read_text()
        for path in paths
        for item in ([path] if path.is_file() else path.rglob("*"))
        if item.is_file()
    ).lower()
    assert "spark" not in content
    assert "sec-022" not in content
