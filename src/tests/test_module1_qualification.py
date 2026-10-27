from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.module1_compatibility import REQUIRED_CONTROLLERS, REQUIRED_CRDS
from scripts.module1_qualification_preflight import GIB, validate_resources
from scripts.prepare_module1_manifests import IMAGE_DIGESTS, prepare
from scripts.render_module1_inventory import build_inventory
from scripts import verify_module1_upstream_inventory as upstream_inventory

ROOT = Path(__file__).parents[2]
QUALIFICATION = ROOT / "qualification/module1"


def test_resource_preflight_accepts_budget_and_rejects_each_shortage() -> None:
    valid = {"memory": 10 * GIB, "cpus": 4, "disk": 30 * GIB, "docker_memory": 10 * GIB,
             "docker_cpus": 4, "docker_disk": 30 * GIB}
    validate_resources(**valid)
    for values, message in (
        ({**valid, "memory": 10 * GIB - 1}, "memory"),
        ({**valid, "cpus": 3}, "CPUs"),
        ({**valid, "docker_cpus": 3}, "CPUs"),
        ({**valid, "disk": 30 * GIB - 1}, "disk"),
        ({**valid, "docker_disk": 30 * GIB - 1}, "disk"),
        ({**valid, "docker_memory": 10 * GIB - 1}, "memory"),
    ):
        with pytest.raises(RuntimeError, match=message):
            validate_resources(**values)


def test_rendered_inventory_hashes_resources_and_records_kustomize(tmp_path: Path) -> None:
    manifest = tmp_path / "component.yaml"
    manifest.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: exact\n  namespace: test\n")
    inventory = build_inventory("a" * 40, {"component": manifest})
    assert inventory["method"] == "kustomize"
    assert inventory["source_commit"] == "a" * 40
    assert inventory["rendered_manifests"]["component"]
    assert inventory["resource_identities"] == [
        {"apiVersion": "v1", "kind": "ConfigMap", "namespace": "test", "name": "exact"}
    ]


def test_manifest_preparation_pins_images_and_omits_only_kernel_agent(tmp_path: Path) -> None:
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    images = list(IMAGE_DIGESTS)
    documents = [
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": f"workload-{index}"},
         "spec": {"template": {"spec": {"containers": [{"name": "main", "image": image}]}}}}
        for index, image in enumerate(images)
    ]
    documents.append({"apiVersion": "apps/v1", "kind": "DaemonSet",
                      "metadata": {"name": "kserve-kernelcachenode-agent", "namespace": "kserve"}})
    for index, name in enumerate(("cert-manager.yaml", "istio-crds.yaml", "istio-namespace.yaml", "istio.yaml",
                                  "knative-serving.yaml", "cluster-local-gateway.yaml", "kserve.yaml")):
        (source / name).write_text(yaml.safe_dump_all(documents if index == 0 else []))
    evidence = prepare(source, output)
    rendered = "".join(path.read_text() for path in output.glob("*.yaml"))
    assert all(f"@{digest}" in rendered for digest in IMAGE_DIGESTS.values())
    assert "kserve-kernelcachenode-agent" not in rendered
    assert evidence["excluded_resources"] == [
        {"kind": "DaemonSet", "namespace": "kserve", "name": "kserve-kernelcachenode-agent"}
    ]
    first = next(iter(IMAGE_DIGESTS))
    (source / "cert-manager.yaml").write_text((source / "cert-manager.yaml").read_text().replace(first, "missing:tag"))
    with pytest.raises(ValueError, match="preparation mismatch"):
        prepare(source, tmp_path / "invalid-output")


def test_upstream_inventory_rejects_permissive_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upstream_inventory, "REQUIRED_CONTROLLERS", set())
    monkeypatch.setattr(upstream_inventory, "REQUIRED_CRDS", set())
    with pytest.raises(ValueError, match="allow-all"):
        upstream_inventory.verify(
            [{"kind": "AuthorizationPolicy", "metadata": {"name": "unsafe", "namespace": "user"}, "spec": {"rules": [{}]}}]
        )


def test_qualification_client_is_restricted_digest_pinned_and_unprivileged() -> None:
    service_account, pod = list(yaml.safe_load_all((QUALIFICATION / "qualification-client.yaml").read_text()))
    assert {service_account["kind"], pod["kind"]} == {"ServiceAccount", "Pod"}
    assert service_account["automountServiceAccountToken"] is False
    assert pod["spec"]["serviceAccountName"] == "qualification-client"
    assert pod["spec"]["automountServiceAccountToken"] is False
    assert pod["spec"]["securityContext"] == {
        "runAsNonRoot": True,
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    container = pod["spec"]["containers"][0]
    assert "@sha256:" in container["image"]
    assert container["securityContext"]["allowPrivilegeEscalation"] is False
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"] == {"drop": ["ALL"]}
    assert container["resources"]["requests"] and container["resources"]["limits"]


def test_scripts_require_authorization_context_and_bounded_cold_start() -> None:
    install = (QUALIFICATION / "install.sh").read_text()
    qualify = (QUALIFICATION / "qualify.sh").read_text()
    capture = (ROOT / "scripts/capture_module1_runtime.sh").read_text()
    assert "--execute" in install and "kind get clusters" not in install
    assert "module1_qualification_preflight.py --execute" in install
    assert "prepare_module1_manifests.py" in install
    assert "python -m scripts.verify_module1_upstream_inventory" in install
    assert "kind delete" not in install + qualify
    assert 'kubectl --context "$context"' in install
    assert 'k=(kubectl --context "$context")' in qualify + capture
    assert "--retry" not in qualify
    assert "--connect-timeout 3" in qualify and '--max-time "$deadline"' in qualify
    assert "COLD_ACTIVATION_READY" in qualify and "POST_ACTIVATION_INFERENCE" in qualify
    assert "networking.knative.dev/visibility: cluster-local" in qualify
    assert "AuthorizationPolicy" not in qualify
    assert all(controller in capture for controller in REQUIRED_CONTROLLERS)


def test_pinned_inventory_matches_required_workloads_and_crd_count() -> None:
    inventory = json.loads((ROOT / "docs/module1/upstream-source-inventory.json").read_text())
    assert inventory["source_commit"] == "f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0"
    assert inventory["installation_method"] == "kustomize"
    assert set(inventory["rendered_controllers"]) == REQUIRED_CONTROLLERS
    assert inventory["required_crd_count"] == len(REQUIRED_CRDS) == 38
    assert "kserve/kserve-localmodelnode-agent" in inventory["disabled_or_omitted_workloads"]
    assert "kserve/kserve-kernelcachenode-agent" in inventory["disabled_or_omitted_workloads"]


def test_workflow_and_matrix_remain_parseable_blocked_and_standard_safe() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/deploy-module1.yaml").read_text())
    matrix = json.loads((ROOT / "docs/module1/compatibility-matrix.json").read_text())
    standard = yaml.safe_load((ROOT / "helm/cognitive-load-monitor/values.yaml").read_text())
    assert workflow["jobs"]["deploy"]
    assert matrix["qualification_status"] == "BLOCKED"
    assert matrix["selected_candidate"] is None
    assert standard["kserve"]["deploymentMode"] == "Standard"
