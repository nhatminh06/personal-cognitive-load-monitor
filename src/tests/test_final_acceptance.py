from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.final_acceptance import CHECKS, RUNTIME_PREREQUISITES, run_offline, validate


ROOT = Path(__file__).parents[2]


def successful_runner(command, **_kwargs):
    return SimpleNamespace(returncode=0, stdout="44 passed\n", stderr="")


def failed_runner(command, **_kwargs):
    return SimpleNamespace(returncode=1, stdout="1 failed\n", stderr="failure")


def offline_report(tmp_path: Path) -> tuple[Path, dict]:
    path = run_offline(ROOT, tmp_path, runner=successful_runner)
    return path, json.loads(path.read_text())


def test_offline_runner_is_explicitly_blocked_from_runtime_claims(tmp_path: Path) -> None:
    path, report = offline_report(tmp_path)
    assert report["local_validation"]["status"] == "PASS"
    assert report["authorization"] == {"cloud_operations_authorized": False}
    assert report["uncompleted_criteria"] == list(CHECKS)
    assert {item["status"] for item in report["checks"].values()} == {"BLOCKED"}
    assert validate(path) == report


def test_offline_runner_records_contract_failure(tmp_path: Path) -> None:
    path = run_offline(ROOT, tmp_path, runner=failed_runner)
    report = validate(path)
    assert report["local_validation"]["status"] == "FAIL"


def test_validator_rejects_tampered_local_evidence(tmp_path: Path) -> None:
    path, _ = offline_report(tmp_path)
    (tmp_path / "offline-contract-tests.txt").write_text("fabricated")
    with pytest.raises(ValueError, match="digest mismatch"):
        validate(path)


def test_validator_rejects_local_runtime_pass(tmp_path: Path) -> None:
    path, report = offline_report(tmp_path)
    report["checks"][CHECKS[0]] = {
        "status": "PASS", "scope": "runtime", "evidence": report["local_validation"]["evidence"],
    }
    report["uncompleted_criteria"] = list(CHECKS[1:])
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="unauthorized"):
        validate(path)


def test_validator_requires_every_runtime_security_gate(tmp_path: Path) -> None:
    path, report = offline_report(tmp_path)
    report.update({
        "environment": {"kind": "gke_runtime", "identity": "projects/p/locations/r/clusters/c"},
        "authorization": {"cloud_operations_authorized": True},
        "prerequisites": {name: True for name in sorted(RUNTIME_PREREQUISITES)},
    })
    report["prerequisites"]["model_approved"] = False
    report["checks"][CHECKS[0]] = {
        "status": "PASS", "scope": "runtime", "evidence": report["local_validation"]["evidence"],
    }
    report["uncompleted_criteria"] = list(CHECKS[1:])
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="security prerequisite"):
        validate(path)


def test_validator_requires_stage_specific_runtime_identity(tmp_path: Path) -> None:
    path, report = offline_report(tmp_path)
    report.update({
        "environment": {"kind": "gke_runtime", "identity": "projects/p/locations/r/clusters/c"},
        "authorization": {"cloud_operations_authorized": True},
        "prerequisites": {name: True for name in sorted(RUNTIME_PREREQUISITES)},
        "identities": {
            "images": {"api": "us-central1-docker.pkg.dev/example-project/cogniflow-images/api@sha256:" + "a" * 64},
            "model": {
                "approval_status": "approved", "artifact_sha256": "b" * 64,
                "package_sha256": "c" * 64, "dataset_sha256": "d" * 64,
            },
            "dataset": None, "kfp_run_id": None, "mlflow": None, "gcs": None,
            "kubernetes_resources": {},
        },
    })
    report["checks"]["gcs_artifact_integrity"] = {
        "status": "PASS", "scope": "runtime", "evidence": report["local_validation"]["evidence"],
    }
    report["uncompleted_criteria"] = [
        name for name in CHECKS if name != "gcs_artifact_integrity"
    ]
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="GCS runtime PASS"):
        validate(path)


def test_validator_rejects_unsupported_or_inconsistent_claims(tmp_path: Path) -> None:
    path, report = offline_report(tmp_path)
    mutated = deepcopy(report)
    mutated["checks"][CHECKS[0]]["status"] = "SIMULATED_PASS"
    path.write_text(json.dumps(mutated))
    with pytest.raises(ValueError, match="invalid acceptance status"):
        validate(path)

    report["uncompleted_criteria"] = []
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="uncompleted criteria"):
        validate(path)
