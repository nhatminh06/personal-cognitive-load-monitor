from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.module1_crd_order import apply_staged, split_manifest


def knative_manifest(path: Path, *, served: bool = True, omit_crd: bool = False) -> Path:
    documents = []
    contracts = (
        ("caching.internal.knative.dev", "images.caching.internal.knative.dev", "Image", "queue-proxy"),
        (
            "networking.internal.knative.dev",
            "certificates.networking.internal.knative.dev",
            "Certificate",
            "routing-serving-certs",
        ),
    )
    for index, (group, crd_name, kind, name) in enumerate(contracts):
        if not (omit_crd and index == 0):
            documents.append({
                "apiVersion": "apiextensions.k8s.io/v1",
                "kind": "CustomResourceDefinition",
                "metadata": {"name": crd_name},
                "spec": {
                    "group": group,
                    "names": {"kind": kind, "plural": crd_name.split(".")[0]},
                    "scope": "Namespaced",
                    "versions": [{"name": "v1alpha1", "served": served, "storage": True}],
                },
            })
        documents.append({
            "apiVersion": f"{group}/v1alpha1",
            "kind": kind,
            "metadata": {"name": name, "namespace": "knative-serving"},
        })
    path.write_text(yaml.safe_dump_all(documents, explicit_start=True, sort_keys=False))
    return path


class Runner:
    def __init__(self, *, discovery_failures: int = 0, wait_failure: bool = False,
                 apply_failure: bool = False, live_version: str = "v1alpha1") -> None:
        self.commands: list[list[str]] = []
        self.discovery_failures = discovery_failures
        self.wait_failure = wait_failure
        self.apply_failure = apply_failure
        self.live_version = live_version

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[-2:] == ["apply", "-f"]:  # pragma: no cover - defensive; paths follow -f
            raise AssertionError("malformed apply")
        if "apply" in command and self.apply_failure:
            raise subprocess.CalledProcessError(1, command, stderr="apply failed")
        if "wait" in command and self.wait_failure:
            return subprocess.CompletedProcess(command, 0, "", "")
        if "get" in command and "crd" in command:
            status = "False" if self.wait_failure else "True"
            live = {
                "status": {"conditions": [{"type": "Established", "status": status}]},
                "spec": {"versions": [{"name": self.live_version, "served": True}]},
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(live), "")
        if "--raw" in command and self.discovery_failures:
            self.discovery_failures -= 1
            return subprocess.CompletedProcess(command, 1, "", "not discovered")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_split_rejects_missing_crd_and_unsupported_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one CRD"):
        split_manifest(knative_manifest(tmp_path / "missing.yaml", omit_crd=True), "knative", tmp_path / "missing")
    with pytest.raises(ValueError, match="does not serve v1alpha1"):
        split_manifest(knative_manifest(tmp_path / "unsupported.yaml", served=False), "knative", tmp_path / "unsupported")


def test_staged_apply_waits_for_established_and_api_discovery(tmp_path: Path) -> None:
    runner = Runner(discovery_failures=2)
    output = tmp_path / "stage"
    apply_staged(
        context="kind-test", manifest=knative_manifest(tmp_path / "knative.yaml"),
        component="knative", output_dir=output, runner=runner, sleeper=lambda _: None,
    )
    commands = [" ".join(command) for command in runner.commands]
    assert commands[0].endswith("apply -f " + str(output / "crds.yaml"))
    assert sum(" --raw " in command for command in commands) == 4
    assert commands[-1].endswith("apply -f " + str(output / "resources.yaml"))
    assert json.loads((output / "result.json").read_text())["status"] == "PASS"


def test_staged_apply_fails_closed_for_unestablished_crd_and_discovery_timeout(tmp_path: Path) -> None:
    manifest = knative_manifest(tmp_path / "knative.yaml")
    for name, runner in (
        ("unestablished", Runner(wait_failure=True)),
        ("unsupported-version", Runner(live_version="v1")),
        ("discovery", Runner(discovery_failures=99)),
    ):
        output = tmp_path / name
        with pytest.raises(RuntimeError):
            apply_staged(
                context="kind-test", manifest=manifest, component="knative", output_dir=output,
                runner=runner, sleeper=lambda _: None, discovery_attempts=2,
            )
        assert json.loads((output / "result.json").read_text())["status"] == "FAIL"
        assert not any(command[-1] == str(output / "resources.yaml") for command in runner.commands)


def test_staged_apply_records_apply_failure(tmp_path: Path) -> None:
    output = tmp_path / "stage"
    with pytest.raises(subprocess.CalledProcessError):
        apply_staged(
            context="kind-test", manifest=knative_manifest(tmp_path / "knative.yaml"),
            component="knative", output_dir=output, runner=Runner(apply_failure=True),
        )
    assert json.loads((output / "result.json").read_text())["status"] == "FAIL"


def test_stage_is_non_overwriting_and_preserves_manifest_evidence(tmp_path: Path) -> None:
    manifest = knative_manifest(tmp_path / "knative.yaml")
    output = tmp_path / "stage"
    evidence = split_manifest(manifest, "knative", output)
    before = (output / "evidence.json").read_bytes()
    assert evidence["original"]["sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert len(evidence["original"]["resources"]) == (
        len(evidence["crds"]["resources"]) + len(evidence["resources"]["resources"])
    )
    assert {item["served_versions"][0] for item in evidence["crds"]["expected"]} == {"v1alpha1"}
    with pytest.raises(FileExistsError):
        apply_staged(context="kind-test", manifest=manifest, component="knative", output_dir=output)
    assert (output / "evidence.json").read_bytes() == before
