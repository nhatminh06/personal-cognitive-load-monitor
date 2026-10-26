import hashlib
from types import SimpleNamespace

import pytest

from scripts.approve_model_candidate import approve_candidate


class Client:
    def __init__(self, tags):
        self.tags = tags
        self.updated = []

    def get_model_version(self, _name, _version):
        return SimpleNamespace(tags=self.tags, source="models/model/1/artifacts")

    def set_model_version_tag(self, *values):
        self.updated.append(values)


def artifact(tmp_path):
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "MLmodel").write_text("model")
    digest = hashlib.sha256()
    name = b"MLmodel"
    payload = b"model"
    digest.update(len(name).to_bytes(8, "big"))
    digest.update(name)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    return root, digest.hexdigest()


def test_candidate_approval_requires_status_and_verified_artifact(monkeypatch, tmp_path):
    root, digest = artifact(tmp_path)
    client = Client({"approval_status": "candidate", "registered_artifact_sha256": digest})
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    monkeypatch.setattr("mlflow.artifacts.download_artifacts", lambda **_: str(root))
    approve_candidate("model", "1", digest, "owner")
    assert ("model", "1", "approval_status", "approved") in client.updated

    monkeypatch.setattr("mlflow.MlflowClient", lambda: Client({"approval_status": "candidate", "registered_artifact_sha256": "bad"}))
    with pytest.raises(ValueError, match="digest mismatch"):
        approve_candidate("model", "1", digest, "owner")

    monkeypatch.setattr("mlflow.MlflowClient", lambda: Client({"approval_status": "approved", "registered_artifact_sha256": digest}))
    with pytest.raises(ValueError, match="not an unapproved"):
        approve_candidate("model", "1", digest, "owner")

    (root / "MLmodel").write_text("tampered")
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    with pytest.raises(ValueError, match="integrity verification failed"):
        approve_candidate("model", "1", digest, "owner")
