from __future__ import annotations

from types import SimpleNamespace

import pytest

from cogniflow_data.training import sha256_tree
from scripts.package_approved_model import package_approved_model


def registry(tmp_path, *, status="approved", name="model", version="7", params=None):
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "model.skops").write_bytes(b"verified-model")
    (artifact / "MLmodel").write_text(
        "flavors:\n  sklearn:\n    serialization_format: skops\n    pickled_model: model.skops\n"
    )
    digest = sha256_tree(artifact)
    tags = {
        "approval_status": status,
        "approved_by": "owner",
        "approved_at": "2026-10-26T00:00:00+00:00",
        "registered_artifact_sha256": digest,
    }
    candidate = SimpleNamespace(
        name=name,
        version=version,
        tags=tags,
        source="models:/immutable-source",
        run_id="run-1",
    )
    run = SimpleNamespace(
        data=SimpleNamespace(
            params=params
            or {
                "dataset_sha256": "1" * 64,
                "git_revision": "2" * 40,
                "feature_schema_version": "1.0",
                "label_provenance": "synthetic_proxy",
            }
        )
    )
    client = SimpleNamespace(
        get_model_version=lambda *_: candidate,
        get_run=lambda *_: run,
    )
    return artifact, digest, candidate, client


def test_packages_exact_approved_artifact_without_loading(monkeypatch, tmp_path):
    artifact, digest, _, client = registry(tmp_path)
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    monkeypatch.setattr("mlflow.artifacts.download_artifacts", lambda **_: str(artifact))
    monkeypatch.setattr("skops.io.load", lambda *args, **kwargs: pytest.fail("must not deserialize"))

    output = tmp_path / "package"
    manifest = package_approved_model("model", "7", digest, output)

    assert (output / "cognitive_load_model.skops").read_bytes() == b"verified-model"
    assert manifest["registered_artifact_sha256"] == digest
    assert manifest["approval_status"] == "approved"
    assert manifest["packaged_model_sha256"] != digest
    assert manifest["model_version"] == "7"


@pytest.mark.parametrize("status", ["candidate", "rejected"])
def test_packaging_rejects_unapproved_version(monkeypatch, tmp_path, status):
    artifact, digest, _, client = registry(tmp_path, status=status)
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    with pytest.raises(ValueError, match="not explicitly approved"):
        package_approved_model("model", "7", digest, tmp_path / "package")


@pytest.mark.parametrize(
    "model_name",
    ["Uppercase", "has.dot", "has_underscore", "-leading", "trailing-", "a" * 64],
)
def test_packaging_rejects_names_incompatible_with_kserve(monkeypatch, tmp_path, model_name):
    monkeypatch.setattr("mlflow.MlflowClient", lambda: pytest.fail("must fail before MLflow"))
    with pytest.raises(ValueError, match="lowercase DNS label"):
        package_approved_model(model_name, "7", "a" * 64, tmp_path / "package")


def test_packaging_rejects_identity_digest_and_artifact_mismatch(monkeypatch, tmp_path):
    artifact, digest, candidate, client = registry(tmp_path)
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    monkeypatch.setattr("mlflow.artifacts.download_artifacts", lambda **_: str(artifact))

    candidate.name = "other"
    with pytest.raises(ValueError, match="different model identity"):
        package_approved_model("model", "7", digest, tmp_path / "identity")

    candidate.name = "model"
    candidate.tags["registered_artifact_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest tag mismatch"):
        package_approved_model("model", "7", digest, tmp_path / "tag")

    candidate.tags["registered_artifact_sha256"] = digest
    (artifact / "model.skops").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity verification failed"):
        package_approved_model("model", "7", digest, tmp_path / "artifact-mismatch")


def test_packaging_rejects_missing_run_identity(monkeypatch, tmp_path):
    _, digest, candidate, client = registry(tmp_path)
    candidate.run_id = None
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)

    with pytest.raises(ValueError, match="run identity is missing"):
        package_approved_model("model", "7", digest, tmp_path / "package")


def test_packaging_rejects_incomplete_provenance(monkeypatch, tmp_path):
    artifact, digest, _, client = registry(tmp_path, params={"dataset_sha256": "1" * 64})
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    monkeypatch.setattr("mlflow.artifacts.download_artifacts", lambda **_: str(artifact))
    with pytest.raises(ValueError, match="provenance is incomplete"):
        package_approved_model("model", "7", digest, tmp_path / "package")


def test_packaging_rejects_unsupported_feature_schema(monkeypatch, tmp_path):
    params = {
        "dataset_sha256": "1" * 64,
        "git_revision": "2" * 40,
        "feature_schema_version": "2.0",
        "label_provenance": "synthetic_proxy",
    }
    artifact, digest, _, client = registry(tmp_path, params=params)
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    monkeypatch.setattr("mlflow.artifacts.download_artifacts", lambda **_: str(artifact))

    with pytest.raises(ValueError, match="feature schema is unsupported"):
        package_approved_model("model", "7", digest, tmp_path / "package")
