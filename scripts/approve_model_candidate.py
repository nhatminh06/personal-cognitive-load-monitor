"""Explicitly approve an MLflow candidate without deploying it."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import mlflow

from cogniflow_data.training import sha256_tree
from preprocessing_api.features import FEATURE_NAMES


IMAGE_PATTERN = re.compile(r"^[a-z0-9./:_-]+@sha256:[0-9a-f]{64}$")
REPOSITORY = "nhatminh06/personal-cognitive-load-monitor"


def approve_candidate(
    model_name: str,
    version: str,
    expected_run_id: str,
    expected_digest: str,
    *,
    repository: str,
    workflow: str,
    workflow_run_id: str,
    git_commit: str,
    environment: str,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", expected_run_id):
        raise ValueError("expected run ID must be a lowercase MLflow run ID")
    if not re.fullmatch(r"[0-9]+", workflow_run_id):
        raise ValueError("GitHub workflow run ID must be numeric")
    if not re.fullmatch(r"[0-9a-f]{40}", git_commit):
        raise ValueError("approval Git commit must be a full SHA")
    if environment != "production-release":
        raise ValueError("approval requires the protected production-release environment")
    if repository != REPOSITORY:
        raise ValueError("approval requires the intended repository")
    expected_workflow = f"{repository}/.github/workflows/release.yaml@refs/heads/main"
    if workflow != expected_workflow:
        raise ValueError("approval requires the main-branch release workflow")

    client = mlflow.MlflowClient()
    candidate = client.get_model_version(model_name, version)
    if (
        candidate.name != model_name
        or str(candidate.version) != version
        or candidate.run_id != expected_run_id
    ):
        raise ValueError("registry returned a different model identity")
    tags = candidate.tags
    if tags.get("approval_status") != "candidate":
        raise ValueError("model version is not an unapproved candidate")
    recorded_digest = tags.get("registered_artifact_sha256")
    if recorded_digest != expected_digest:
        raise ValueError("candidate digest mismatch")
    run = client.get_run(expected_run_id)
    params = run.data.params
    required = {
        "dataset_sha256": r"[0-9a-f]{64}",
        "git_revision": r"[0-9a-f]{40}",
        "feature_schema_version": r"1\.0",
        "label_provenance": r"synthetic_proxy",
        "kfp_pipeline_name": r"cogniflow-kubeflow-training",
        "kfp_run_id": r".+",
        "component_image": IMAGE_PATTERN.pattern,
    }
    if any(not re.fullmatch(pattern, params.get(key, "")) for key, pattern in required.items()):
        raise ValueError("candidate run provenance is incomplete")
    if params["git_revision"] != git_commit:
        raise ValueError("candidate Git revision differs from the reviewed release commit")
    if any(tags.get(key) != params[key] for key in required):
        raise ValueError("candidate run and model-version provenance disagree")

    manifest_path = mlflow.artifacts.download_artifacts(
        run_id=expected_run_id,
        artifact_path="dataset-manifest.json",
    )
    manifest = json.loads(Path(manifest_path).read_text())
    if (
        manifest.get("dataset_sha256") != params["dataset_sha256"]
        or manifest.get("git_revision") != params["git_revision"]
        or manifest.get("feature_schema_version") != "1.0"
        or manifest.get("feature_names") != list(FEATURE_NAMES)
        or manifest.get("label_provenance") != "synthetic_proxy"
    ):
        raise ValueError("candidate dataset manifest provenance is inconsistent")

    artifact_path = mlflow.artifacts.download_artifacts(artifact_uri=candidate.source)
    if sha256_tree(Path(artifact_path)) != expected_digest:
        raise ValueError("registered artifact integrity verification failed")
    approval_tags = {
        "approval_scope": "synthetic_proxy_engineering_only",
        "approval_repository": repository,
        "approval_workflow": workflow,
        "approval_workflow_run_id": workflow_run_id,
        "approval_git_commit": git_commit,
        "approval_environment": environment,
        "approved_by": f"github-environment:{environment}",
        "approved_at": datetime.now(UTC).isoformat(),
    }
    for key, value in approval_tags.items():
        client.set_model_version_tag(model_name, version, key, value)
    client.set_model_version_tag(model_name, version, "approval_status", "approved")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--environment", required=True)
    args = parser.parse_args()
    if not args.approve:
        raise SystemExit("approval requires the explicit --approve flag")
    mlflow.set_tracking_uri(args.tracking_uri)
    approve_candidate(
        args.model_name,
        args.version,
        args.expected_run_id,
        args.expected_digest,
        repository=args.repository,
        workflow=args.workflow,
        workflow_run_id=args.workflow_run_id,
        git_commit=args.git_commit,
        environment=args.environment,
    )


if __name__ == "__main__":
    main()
