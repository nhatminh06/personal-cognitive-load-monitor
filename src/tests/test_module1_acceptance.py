from __future__ import annotations

from pathlib import Path

import pytest

from scripts.module1_acceptance import CRITERIA, render_report, validate_evidence, write_report


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
                "evidence": f"evidence/{criterion}.json",
            }
            for criterion in CRITERIA
        },
        "replicas": {"kserve_idle": 0, "kserve_cold_start": 1, "hpa_initial": 2, "hpa_peak": 4, "hpa_final": 2},
    }


def test_complete_cloud_evidence_is_accepted_and_report_is_exclusive(tmp_path: Path) -> None:
    payload = evidence()
    validate_evidence(payload, payload["identity"]["kubernetes_context"], True)
    report = tmp_path / "report.md"
    write_report(report, render_report(payload))
    assert report.stat().st_mode & 0o777 == 0o600
    assert "kserve scale to zero | cloud_runtime_verified" in report.read_text()
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
        "evidence": "pending separate cloud authorization",
    }
    context = payload["identity"]["kubernetes_context"]
    validate_evidence(payload, context, False)
    with pytest.raises(ValueError, match="kserve_scale_to_zero"):
        validate_evidence(payload, context, True)


def test_evidence_rejects_secret_bearing_fields() -> None:
    payload = evidence()
    payload["api_token"] = "must-not-be-recorded"
    with pytest.raises(ValueError, match="secret-bearing"):
        validate_evidence(payload, payload["identity"]["kubernetes_context"], False)
