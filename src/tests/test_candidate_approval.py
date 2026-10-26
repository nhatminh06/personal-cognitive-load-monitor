from types import SimpleNamespace

import pytest

from scripts.approve_model_candidate import approve_candidate


class Client:
    def __init__(self, tags):
        self.tags = tags
        self.updated = []

    def get_model_version(self, _name, _version):
        return SimpleNamespace(tags=self.tags)

    def set_model_version_tag(self, *values):
        self.updated.append(values)


def test_candidate_approval_requires_status_and_digest(monkeypatch):
    client = Client({"approval_status": "candidate", "model_sha256": "abc"})
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    approve_candidate("model", "1", "abc", "owner")
    assert ("model", "1", "approval_status", "approved") in client.updated

    monkeypatch.setattr("mlflow.MlflowClient", lambda: Client({"approval_status": "candidate", "model_sha256": "bad"}))
    with pytest.raises(ValueError, match="digest mismatch"):
        approve_candidate("model", "1", "abc", "owner")

    monkeypatch.setattr("mlflow.MlflowClient", lambda: Client({"approval_status": "approved", "model_sha256": "abc"}))
    with pytest.raises(ValueError, match="not an unapproved"):
        approve_candidate("model", "1", "abc", "owner")
