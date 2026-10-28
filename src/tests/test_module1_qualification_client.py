from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.module1_qualification_client import apply_client, validate

ROOT = Path(__file__).parents[2]
SERVICE_ACCOUNT = ROOT / "qualification/module1/qualification-client-serviceaccount.yaml"
POD = ROOT / "qualification/module1/qualification-client.yaml"


class Runner:
    def __init__(self, *, fail_service_account: bool = False, fail_admission: bool = False) -> None:
        self.commands: list[list[str]] = []
        self.fail_service_account = fail_service_account
        self.fail_admission = fail_admission

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if self.fail_service_account and "apply" in command and str(SERVICE_ACCOUNT) in command:
            raise subprocess.CalledProcessError(1, command)
        if self.fail_admission and "--dry-run=server" in command:
            raise subprocess.CalledProcessError(1, command)
        if "get" in command and "serviceaccount" in command:
            resource = {
                "metadata": {"name": "qualification-client", "namespace": "cogniflow-qualification"},
                "automountServiceAccountToken": False,
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(resource), "")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_client_validation_rejects_missing_service_account_and_wrong_namespace(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        validate(tmp_path / "missing.yaml", POD)
    resource = yaml.safe_load(SERVICE_ACCOUNT.read_text())
    resource["metadata"]["namespace"] = "default"
    wrong = tmp_path / "serviceaccount.yaml"
    wrong.write_text(yaml.safe_dump(resource))
    with pytest.raises(ValueError, match="cogniflow-qualification/qualification-client"):
        validate(wrong, POD)


def test_service_account_creation_failure_stops_before_pod() -> None:
    runner = Runner(fail_service_account=True)
    with pytest.raises(subprocess.CalledProcessError):
        apply_client(
            context="kind-cogniflow-module1-qualification",
            service_account_path=SERVICE_ACCOUNT,
            pod_path=POD,
            runner=runner,
        )
    assert len(runner.commands) == 1


def test_pod_admission_failure_stops_before_pod_apply() -> None:
    runner = Runner(fail_admission=True)
    with pytest.raises(subprocess.CalledProcessError):
        apply_client(
            context="kind-cogniflow-module1-qualification",
            service_account_path=SERVICE_ACCOUNT,
            pod_path=POD,
            runner=runner,
        )
    assert "--dry-run=server" in runner.commands[-1]
    assert not any("wait" in command for command in runner.commands)


def test_client_order_is_idempotent_after_partial_qualification() -> None:
    runner = Runner(fail_admission=True)
    with pytest.raises(subprocess.CalledProcessError):
        apply_client(
            context="kind-cogniflow-module1-qualification",
            service_account_path=SERVICE_ACCOUNT,
            pod_path=POD,
            runner=runner,
        )
    runner.fail_admission = False
    start = len(runner.commands)
    apply_client(
        context="kind-cogniflow-module1-qualification",
        service_account_path=SERVICE_ACCOUNT,
        pod_path=POD,
        runner=runner,
    )
    retry = runner.commands[start:]
    assert [next(item for item in command if item in {"apply", "get", "wait"}) for command in retry] == [
        "apply", "get", "apply", "apply", "wait",
    ]
    assert str(SERVICE_ACCOUNT) in retry[0]
    assert str(POD) in retry[2] and str(POD) in retry[3]


def test_qualification_fails_closed_on_wrong_dedicated_context(tmp_path: Path) -> None:
    installation = tmp_path / "installation"
    installation.mkdir()
    (installation / "rendered").mkdir()
    (installation / "installation.json").write_text("{}\n")
    (installation / "rendered-manifests.sha256").write_text("")
    (installation / "kubeconfig").write_text("test\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    observed = tmp_path / "observed-kubeconfig"
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(
        f"#!/bin/sh\nprintf '%s' \"$KUBECONFIG\" >'{observed}'\nprintf '%s\\n' wrong-context\n"
    )
    kubectl.chmod(0o755)
    evidence = tmp_path / "attempt"
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "KSERVE_IMAGE": "docker.io/library/cogniflow-kserve@sha256:" + "a" * 64,
    }
    result = subprocess.run(
        [
            "bash", str(ROOT / "qualification/module1/qualify.sh"), "--execute",
            "--installation-evidence", str(installation),
            "--qualification-evidence", str(evidence),
        ],
        cwd=ROOT, env=environment, text=True, capture_output=True,
    )
    assert result.returncode != 0
    assert observed.read_text() == str(installation / "kubeconfig")
    assert json.loads((evidence / "qualification-result.json").read_text())["status"] == "FAIL"
