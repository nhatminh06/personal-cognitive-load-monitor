from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.module1_acceptance import CRITERIA, render_report, validate_evidence, verify_artifacts, write_report


def evidence() -> dict:
    digest = "a" * 64
    return {
        "schema_version": "1.0",
        "identity": {
            "git_commit": "1" * 40,
            "kubernetes_context": "gke_project_us-central1_cogniflow",
            "cluster_uid": "cluster-uid",
            "namespace": "cogniflow",
            "namespace_uid": "namespace-uid",
        },
        "release": {
            "api_image": f"us-central1-docker.pkg.dev/project-1/cogniflow-images/api@sha256:{digest}",
            "kserve_image": f"us-central1-docker.pkg.dev/project-1/cogniflow-images/kserve@sha256:{digest}",
            "model": {
                "name": "cognitive-load-classifier",
                "version": "1",
                "model_sha256": digest,
                "artifact_sha256": digest,
                "dataset_sha256": digest,
            },
        },
        "checks": {
            criterion: {
                "status": "ci_verified" if criterion == "ci_cd" else "cloud_runtime_verified",
                "evidence": {"path": f"{criterion}.json", "sha256": "0" * 64},
            }
            for criterion in CRITERIA
        },
        "replicas": {
            "kserve_idle": 0, "kserve_cold_start": 1, "kserve_cold_start_seconds": 12.5,
            "kserve_prediction_succeeded": True,
            "hpa_initial": 2, "hpa_peak": 4, "hpa_final": 2,
        },
    }


def write_artifacts(payload: dict, root: Path) -> None:
    root.mkdir()
    for criterion in CRITERIA:
        path = root / f"{criterion}.json"
        path.write_text(json.dumps({"criterion": criterion, "result": "passed"}) + "\n")
        payload["checks"][criterion]["evidence"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def test_complete_cloud_evidence_is_accepted_and_report_is_exclusive(tmp_path: Path) -> None:
    payload = evidence()
    artifact_root = tmp_path / "artifacts"
    write_artifacts(payload, artifact_root)
    validate_evidence(payload, payload["identity"]["kubernetes_context"], True)
    verified = verify_artifacts(payload, artifact_root)
    report = tmp_path / "report.md"
    write_report(report, render_report(payload, verified))
    assert report.stat().st_mode & 0o777 == 0o600
    assert "kserve scale to zero | cloud_runtime_verified" in report.read_text()
    assert "INDEPENDENT RUNTIME REVIEW REQUIRED" in report.read_text()
    with pytest.raises(FileExistsError):
        write_report(report, "replacement")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("context", "wrong", "Kubernetes context"),
        ("api_image", "registry.example/api:latest", "immutable Artifact Registry"),
        ("model_name", "Uppercase.Model", "DNS-label"),
        ("artifact_digest", "0" * 63, "SHA-256"),
    ),
)
def test_evidence_rejects_wrong_identity_mutable_images_and_invalid_model(field, value, message) -> None:
    payload = evidence()
    expected_context = payload["identity"]["kubernetes_context"]
    if field == "context":
        expected_context = value
    elif field == "api_image":
        payload["release"]["api_image"] = value
    elif field == "model_name":
        payload["release"]["model"]["name"] = value
    else:
        payload["release"]["model"]["artifact_sha256"] = value
    with pytest.raises(ValueError, match=message):
        validate_evidence(payload, expected_context, True)


def test_source_report_allows_explicit_pending_but_cloud_gate_does_not() -> None:
    payload = evidence()
    payload["checks"]["kserve_scale_to_zero"] = {
        "status": "blocked",
        "evidence": {"path": "kserve_scale_to_zero.json", "sha256": "0" * 64},
    }
    context = payload["identity"]["kubernetes_context"]
    validate_evidence(payload, context, False)
    with pytest.raises(ValueError, match="kserve_scale_to_zero"):
        validate_evidence(payload, context, True)


@pytest.mark.parametrize(
    ("field", "value"),
    (("kserve_idle", 1), ("kserve_cold_start", 0), ("kserve_cold_start_seconds", 0),
     ("kserve_cold_start_seconds", float("inf")),
     ("kserve_prediction_succeeded", False)),
)
def test_cloud_acceptance_requires_observed_zero_activation_and_prediction(field, value) -> None:
    payload = evidence()
    payload["replicas"][field] = value
    with pytest.raises(ValueError, match="zero idle replicas"):
        validate_evidence(payload, payload["identity"]["kubernetes_context"], True)


def test_cloud_acceptance_records_slow_success_without_a_grading_deadline() -> None:
    payload = evidence()
    payload["replicas"]["kserve_cold_start_seconds"] = 45.5

    validate_evidence(payload, payload["identity"]["kubernetes_context"], True)


def test_evidence_rejects_secret_bearing_fields() -> None:
    payload = evidence()
    payload["api_token"] = "must-not-be-recorded"
    with pytest.raises(ValueError, match="secret-bearing"):
        validate_evidence(payload, payload["identity"]["kubernetes_context"], False)


def test_artifact_verification_rejects_credential_like_values(tmp_path: Path) -> None:
    payload = evidence()
    root = tmp_path / "artifacts"
    write_artifacts(payload, root)
    artifact = root / "metrics.json"
    artifact.write_text('{"header":"Bearer must-not-be-recorded"}\n')
    payload["checks"]["metrics"]["evidence"]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="credential-like"):
        verify_artifacts(payload, root)


@pytest.mark.parametrize("failure", ("missing", "changed", "duplicate", "traversal", "absolute"))
def test_artifact_verification_rejects_missing_changed_duplicate_and_unsafe_paths(tmp_path: Path, failure: str) -> None:
    payload = evidence()
    root = tmp_path / "artifacts"
    write_artifacts(payload, root)
    if failure == "missing":
        (root / "metrics.json").unlink()
    elif failure == "changed":
        (root / "metrics.json").write_text('{"result":"fabricated"}\n')
    elif failure == "duplicate":
        payload["checks"]["metrics"]["evidence"] = payload["checks"]["tracing"]["evidence"].copy()
    elif failure == "traversal":
        payload["checks"]["metrics"]["evidence"]["path"] = "../metrics.json"
    else:
        payload["checks"]["metrics"]["evidence"]["path"] = str((root / "metrics.json").resolve())
    with pytest.raises(ValueError, match="missing|changed|duplicate|unsafe"):
        verify_artifacts(payload, root)


def test_artifact_verification_rejects_symlinks_and_secret_fields(tmp_path: Path) -> None:
    payload = evidence()
    root = tmp_path / "artifacts"
    write_artifacts(payload, root)
    target = root / "outside.json"
    target.write_text('{"result":"passed"}\n')
    linked = root / "metrics.json"
    linked.unlink()
    linked.symlink_to(target)
    payload["checks"]["metrics"]["evidence"]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="unsafe"):
        verify_artifacts(payload, root)

    linked.unlink()
    linked.write_text('{"api_token":"must-not-be-recorded"}\n')
    payload["checks"]["metrics"]["evidence"]["sha256"] = hashlib.sha256(linked.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="secret-bearing"):
        verify_artifacts(payload, root)


def test_schema_only_report_never_claims_runtime_acceptance() -> None:
    report = render_report(evidence())
    assert "not verified (schema only)" in report
    assert "INDEPENDENT RUNTIME REVIEW REQUIRED" in report
