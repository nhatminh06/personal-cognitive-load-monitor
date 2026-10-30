import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.approve_model_candidate import approve_candidate


RUN_ID = "a" * 32
GIT_REVISION = "b" * 40
IMAGE = "registry.example/cogniflow-kfp@sha256:" + "c" * 64
REPOSITORY = "nhatminh06/personal-cognitive-load-monitor"
WORKFLOW = f"{REPOSITORY}/.github/workflows/release.yaml@refs/heads/main"


class Client:
    def __init__(self, tags):
        self.tags = tags
        self.updated = []
        self.candidate = SimpleNamespace(
            name="model", version="1", run_id=RUN_ID, tags=tags,
            source="models:/immutable-source",
        )
        self.run = SimpleNamespace(data=SimpleNamespace(params={
            "dataset_sha256": "d" * 64,
            "git_revision": GIT_REVISION,
            "feature_schema_version": "1.0",
            "label_provenance": "synthetic_proxy",
            "kfp_pipeline_name": "cogniflow-kubeflow-training",
            "kfp_run_id": "pipeline-run-1",
            "component_image": IMAGE,
        }))

    def get_model_version(self, _name, _version):
        return self.candidate

    def get_run(self, _run_id):
        return self.run

    def set_model_version_tag(self, *values):
        self.updated.append(values)


def artifact(tmp_path):
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "MLmodel").write_text("model")
    digest = hashlib.sha256()
    name, payload = b"MLmodel", b"model"
    digest.update(len(name).to_bytes(8, "big"))
    digest.update(name)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    manifest = tmp_path / "dataset-manifest.json"
    manifest.write_text(json.dumps({
        "dataset_sha256": "d" * 64,
        "git_revision": GIT_REVISION,
        "feature_schema_version": "1.0",
        "feature_names": [
            "focus_minutes", "distraction_minutes", "tasks_due",
            "hours_to_deadline", "focus_ratio", "distraction_ratio",
        ],
        "label_provenance": "synthetic_proxy",
    }))
    return root, manifest, digest.hexdigest()


def approve(digest):
    approve_candidate(
        "model", "1", RUN_ID, digest,
        repository=REPOSITORY,
        workflow=WORKFLOW,
        workflow_run_id="1234",
        git_commit=GIT_REVISION,
        environment="production-release",
    )


def valid_tags(digest):
    return {
        "approval_status": "candidate",
        "registered_artifact_sha256": digest,
        "dataset_sha256": "d" * 64,
        "git_revision": GIT_REVISION,
        "feature_schema_version": "1.0",
        "label_provenance": "synthetic_proxy",
        "kfp_pipeline_name": "cogniflow-kubeflow-training",
        "kfp_run_id": "pipeline-run-1",
        "component_image": IMAGE,
    }


def configure(monkeypatch, client, root, manifest):
    monkeypatch.setattr("mlflow.MlflowClient", lambda: client)
    monkeypatch.setattr(
        "mlflow.artifacts.download_artifacts",
        lambda **kwargs: str(manifest if kwargs.get("artifact_path") else root),
    )


def test_candidate_approval_requires_exact_identity_provenance_and_artifact(
    monkeypatch, tmp_path,
):
    root, manifest, digest = artifact(tmp_path)
    client = Client(valid_tags(digest))
    configure(monkeypatch, client, root, manifest)

    approve(digest)

    assert client.updated[-1] == ("model", "1", "approval_status", "approved")
    assert ("model", "1", "approval_scope", "synthetic_proxy_engineering_only") in client.updated
    assert ("model", "1", "approved_by", "github-environment:production-release") in client.updated


@pytest.mark.parametrize("change,message", [
    ("digest", "digest mismatch"),
    ("status", "not an unapproved"),
    ("run", "different model identity"),
    ("provenance", "provenance disagree"),
    ("manifest", "manifest provenance is inconsistent"),
])
def test_candidate_approval_fails_closed_without_mutation(
    monkeypatch, tmp_path, change, message,
):
    root, manifest, digest = artifact(tmp_path)
    tags = valid_tags(digest)
    client = Client(tags)
    if change == "digest":
        tags["registered_artifact_sha256"] = "0" * 64
    elif change == "status":
        tags["approval_status"] = "approved"
    elif change == "run":
        client.candidate.run_id = "f" * 32
    elif change == "provenance":
        tags["git_revision"] = "0" * 40
    else:
        payload = json.loads(manifest.read_text())
        payload["feature_names"] = []
        manifest.write_text(json.dumps(payload))
    configure(monkeypatch, client, root, manifest)

    with pytest.raises(ValueError, match=message):
        approve(digest)
    assert client.updated == []


def test_candidate_approval_rejects_unprotected_workflow_identity(monkeypatch):
    monkeypatch.setattr("mlflow.MlflowClient", lambda: pytest.fail("must fail before MLflow"))
    with pytest.raises(ValueError, match="production-release"):
        approve_candidate(
            "model", "1", RUN_ID, "d" * 64,
            repository=REPOSITORY,
            workflow=WORKFLOW,
            workflow_run_id="1234",
            git_commit=GIT_REVISION,
            environment="unprotected",
        )
