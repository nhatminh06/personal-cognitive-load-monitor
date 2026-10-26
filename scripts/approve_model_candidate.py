"""Explicitly approve an MLflow candidate without deploying it."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import mlflow

from cogniflow_data.training import sha256_tree


def approve_candidate(model_name: str, version: str, expected_digest: str, actor: str) -> None:
    client = mlflow.MlflowClient()
    candidate = client.get_model_version(model_name, version)
    tags = candidate.tags
    if tags.get("approval_status") != "candidate":
        raise ValueError("model version is not an unapproved candidate")
    recorded_digest = tags.get("registered_artifact_sha256")
    if recorded_digest != expected_digest:
        raise ValueError("candidate digest mismatch")
    artifact_path = mlflow.artifacts.download_artifacts(artifact_uri=candidate.source)
    if sha256_tree(Path(artifact_path)) != expected_digest:
        raise ValueError("registered artifact integrity verification failed")
    client.set_model_version_tag(model_name, version, "approval_status", "approved")
    client.set_model_version_tag(model_name, version, "approved_by", actor)
    client.set_model_version_tag(model_name, version, "approved_at", datetime.now(UTC).isoformat())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-digest", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--tracking-uri", required=True)
    args = parser.parse_args()
    if not args.approve:
        raise SystemExit("approval requires the explicit --approve flag")
    mlflow.set_tracking_uri(args.tracking_uri)
    approve_candidate(args.model_name, args.version, args.expected_digest, args.actor)


if __name__ == "__main__":
    main()
