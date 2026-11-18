"""Publish and independently verify an immutable candidate artifact in GCS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mlflow
from google.cloud import storage

from cogniflow_data.gcs_artifacts import (
    bind_mlflow_candidate,
    publish_candidate,
    validate_mlflow_candidate,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.artifact.suffix != ".skops":
        parser.error("--artifact must be the verified .skops candidate artifact")

    mlflow.set_tracking_uri(args.tracking_uri)
    mlflow_client = mlflow.MlflowClient()
    validate_mlflow_candidate(
        mlflow_client, args.model_name, args.model_version, args.run_id
    )
    # Application Default Credentials are supplied by GKE Workload Identity.
    identity = publish_candidate(
        storage.Client(),
        bucket_name=args.bucket,
        artifact=args.artifact,
        model_name=args.model_name,
        model_version=args.model_version,
        mlflow_run_id=args.run_id,
        source_revision=args.source_revision,
    )
    bind_mlflow_candidate(mlflow_client, identity)
    args.output.write_text(json.dumps(identity.to_dict(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
