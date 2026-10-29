"""Validate the disposable model package and emit its runtime identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from preprocessing_api.model_client import validated_package_manifest

SYNTHETIC_DIGEST = hashlib.sha256(b"cogniflow-module1-qualification").hexdigest()
QUALIFICATION_IDENTITY = {
    "model_name": "qualification-model",
    "model_version": "1",
    "registered_artifact_sha256": SYNTHETIC_DIGEST,
    "dataset_sha256": SYNTHETIC_DIGEST,
    "feature_schema_version": "1.0",
    "run_id": "disposable-qualification",
    "registered_source": "local://disposable-qualification",
    "approved_by": "disposable-qualification-only",
}
ENVIRONMENT_FIELDS = {
    "MODEL_NAME": "model_name",
    "MODEL_VERSION": "model_version",
    "MODEL_ARTIFACT_SHA256": "registered_artifact_sha256",
    "MODEL_DATASET_SHA256": "dataset_sha256",
    "MODEL_FEATURE_SCHEMA_VERSION": "feature_schema_version",
    "MODEL_SHA256": "packaged_model_sha256",
}


def qualification_environment(package: Path) -> dict[str, str]:
    model = package / "cognitive_load_model.skops"
    manifest_path = package / "model-package.json"
    manifest = json.loads(manifest_path.read_text())
    if any(str(manifest.get(name, "")) != value for name, value in QUALIFICATION_IDENTITY.items()):
        raise ValueError("model package is not the disposable qualification identity")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    environment = {
        name: digest if field == "packaged_model_sha256" else QUALIFICATION_IDENTITY[field]
        for name, field in ENVIRONMENT_FIELDS.items()
    }
    previous = {name: os.environ.get(name) for name in environment | {"MODEL_PACKAGE_PATH": ""}}
    try:
        os.environ.update(environment)
        os.environ["MODEL_PACKAGE_PATH"] = str(manifest_path)
        validated_package_manifest(model, digest)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return environment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    environment = qualification_environment(args.package)
    args.output.write_text(json.dumps(environment, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
