"""Package one explicitly approved MLflow model without deserializing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

import mlflow
import yaml

from cogniflow_data.training import sha256_tree
from preprocessing_api.features import FEATURE_NAMES

KSERVE_MODEL_NAME_RE = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")


def package_approved_model(
    model_name: str,
    version: str,
    expected_run_id: str,
    expected_artifact_digest: str,
    output_dir: Path,
) -> dict[str, object]:
    if not KSERVE_MODEL_NAME_RE.fullmatch(model_name):
        raise ValueError("model name must be a lowercase DNS label of at most 63 characters")
    if not version.isdigit() or int(version) < 1:
        raise ValueError("a positive numeric model version is required")
    if not re.fullmatch(r"[0-9a-f]{32}", expected_run_id):
        raise ValueError("expected run ID must be a lowercase MLflow run ID")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_artifact_digest):
        raise ValueError("expected artifact digest must be a lowercase SHA-256")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")

    client = mlflow.MlflowClient()
    candidate = client.get_model_version(model_name, version)
    if str(candidate.version) != version or candidate.name != model_name:
        raise ValueError("registry returned a different model identity")
    if candidate.run_id != expected_run_id:
        raise ValueError("registered model run identity mismatch")
    tags = candidate.tags
    if tags.get("approval_status") != "approved" or not tags.get("approved_by") or not tags.get("approved_at"):
        raise ValueError("model version is not explicitly approved")
    if tags.get("registered_artifact_sha256") != expected_artifact_digest:
        raise ValueError("registered artifact digest tag mismatch")
    if (
        tags.get("approval_scope") != "solo_owner_educational_decision"
        or tags.get("approval_environment") != "production-release"
        or tags.get("approved_by") != "github-owner:nhatminh06"
        or tags.get("approval_repository") != "nhatminh06/personal-cognitive-load-monitor"
        or tags.get("approval_workflow")
        != "nhatminh06/personal-cognitive-load-monitor/.github/workflows/release.yaml@refs/heads/main"
        or not re.fullmatch(r"[0-9]+", tags.get("approval_workflow_run_id", ""))
        or not re.fullmatch(r"[0-9a-f]{40}", tags.get("approval_git_commit", ""))
    ):
        raise ValueError("solo-owner educational authorization provenance is incomplete")

    artifact_dir = Path(mlflow.artifacts.download_artifacts(artifact_uri=candidate.source))
    if sha256_tree(artifact_dir) != expected_artifact_digest:
        raise ValueError("registered MLflow artifact integrity verification failed")
    metadata = yaml.safe_load((artifact_dir / "MLmodel").read_text())
    sklearn = metadata.get("flavors", {}).get("sklearn", {})
    if sklearn.get("serialization_format") != "skops":
        raise ValueError("registered model must use skops serialization")
    model_file = artifact_dir / str(sklearn.get("pickled_model", ""))
    if (
        model_file.parent != artifact_dir
        or model_file.name != "model.skops"
        or not model_file.is_file()
        or model_file.is_symlink()
    ):
        raise ValueError("registered model artifact layout is unsupported")

    run = client.get_run(candidate.run_id)
    params = run.data.params
    required_params = ("dataset_sha256", "git_revision", "feature_schema_version", "label_provenance")
    if any(not params.get(name) for name in required_params):
        raise ValueError("registered model provenance is incomplete")
    if params["feature_schema_version"] != "1.0":
        raise ValueError("registered model feature schema is unsupported")
    if tags["approval_git_commit"] != params["git_revision"]:
        raise ValueError("authorized revision and model provenance disagree")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_dir.parent) as temporary:
        package = Path(temporary) / output_dir.name
        package.mkdir()
        packaged_model = package / "cognitive_load_model.skops"
        shutil.copyfile(model_file, packaged_model)
        packaged_digest = hashlib.sha256(packaged_model.read_bytes()).hexdigest()
        manifest: dict[str, object] = {
            "contract_version": "1.0",
            "approval_status": "approved",
            "approval_scope": tags["approval_scope"],
            "approval_repository": tags["approval_repository"],
            "approval_workflow": tags["approval_workflow"],
            "approval_workflow_run_id": tags["approval_workflow_run_id"],
            "approval_git_commit": tags["approval_git_commit"],
            "approval_environment": tags["approval_environment"],
            "model_name": model_name,
            "model_version": version,
            "run_id": candidate.run_id,
            "registered_source": candidate.source,
            "registered_artifact_sha256": expected_artifact_digest,
            "packaged_model_sha256": packaged_digest,
            "dataset_sha256": params["dataset_sha256"],
            "feature_schema_version": params["feature_schema_version"],
            "feature_names": list(FEATURE_NAMES),
            "label_provenance": params["label_provenance"],
            "git_revision": params["git_revision"],
            "approved_by": tags["approved_by"],
            "approved_at": tags["approved_at"],
        }
        (package / "model-package.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        packaged_model.chmod(0o444)
        (package / "model-package.json").chmod(0o444)
        package.rename(output_dir)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--expected-artifact-digest", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    mlflow.set_tracking_uri(args.tracking_uri)
    print(
        json.dumps(
            package_approved_model(
                args.model_name,
                args.version,
                args.expected_run_id,
                args.expected_artifact_digest,
                args.output_dir,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
