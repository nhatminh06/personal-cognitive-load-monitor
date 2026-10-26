"""Bounded task entrypoints for the Kubeflow Pipelines training graph."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd

from preprocessing_api.features import FEATURE_NAMES

from .historical import HistoricalFeatureRow, SyntheticLabel
from .training import (
    candidate_models,
    evaluate_predictions,
    load_jsonl,
    prepare_training_dataset,
    sha256,
    sha256_tree,
    split_training_frame,
    validate_training_manifest,
)

IMAGE_PATTERN = re.compile(r"^[a-z0-9./:_-]+@sha256:[0-9a-f]{64}$")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def validate_inputs(
    features: Path,
    labels: Path,
    feature_manifest: Path,
    output: Path,
    *,
    expected_git_revision: str,
) -> dict[str, Any]:
    manifest = json.loads(feature_manifest.read_text())
    if manifest.get("sha256") != sha256(features):
        raise ValueError("feature manifest checksum mismatch")
    if manifest.get("feature_schema_version") != "1.0" or manifest.get(
        "feature_names"
    ) != list(FEATURE_NAMES):
        raise ValueError("unsupported feature manifest contract")
    feature_rows = load_jsonl(features, HistoricalFeatureRow)
    label_rows = load_jsonl(labels, SyntheticLabel)
    if manifest.get("row_count") != len(feature_rows) or len(label_rows) != len(feature_rows):
        raise ValueError("feature and label row counts disagree")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_git_revision):
        raise ValueError("git revision must be a full commit SHA")
    built_revision = os.getenv("COGNIFLOW_CODE_REVISION", expected_git_revision)
    if built_revision != expected_git_revision:
        raise ValueError("component image code revision mismatch")
    result = {
        "contract_version": "1.0",
        "validation": "passed",
        "feature_sha256": sha256(features),
        "label_sha256": sha256(labels),
        "feature_manifest_sha256": sha256(feature_manifest),
        "git_revision": expected_git_revision,
        "sample_count": len(feature_rows),
        "feature_schema_version": "1.0",
        "feature_names": list(FEATURE_NAMES),
        "label_provenance": "synthetic_proxy",
    }
    _write_json(output, result)
    return result


def prepare_dataset(
    features: Path,
    labels: Path,
    feature_manifest: Path,
    validation: Path,
    output_dataset: Path,
    output_manifest: Path,
    *,
    training_cutoff: datetime,
    git_revision: str,
) -> dict[str, Any]:
    attestation = json.loads(validation.read_text())
    if (
        attestation.get("validation") != "passed"
        or attestation.get("feature_sha256") != sha256(features)
        or attestation.get("label_sha256") != sha256(labels)
        or attestation.get("feature_manifest_sha256") != sha256(feature_manifest)
        or attestation.get("git_revision") != git_revision
    ):
        raise ValueError("input validation attestation mismatch")
    return prepare_training_dataset(
        features,
        feature_manifest,
        labels,
        output_dataset,
        output_manifest,
        training_cutoff=training_cutoff,
        git_revision=git_revision,
    )


def train_candidates(
    dataset: Path,
    manifest_path: Path,
    output_models: Path,
    output_validation: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    validate_training_manifest(manifest, dataset)
    frame = pd.read_json(dataset, lines=True)
    train_frame, validation_frame, _ = split_training_frame(frame, manifest)
    if len(frame) == 180 and manifest["splits"] != {
        "train": [0, 108],
        "validation": [108, 144],
        "test": [144, 180],
    }:
        raise ValueError("the 180-row fixture requires chronological 108/36/36 splits")
    models = candidate_models()
    validation_metrics: dict[str, Any] = {}
    for name, model in models.items():
        model.fit(train_frame[list(FEATURE_NAMES)], train_frame["label"])
        validation_metrics[name] = evaluate_predictions(
            validation_frame["label"], model.predict(validation_frame[list(FEATURE_NAMES)])
        )
    output_models.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, output_models)
    result = {
        "contract_version": "1.0",
        "dataset_sha256": manifest["dataset_sha256"],
        "models_sha256": sha256(output_models),
        "validation": validation_metrics,
        "split_counts": {"train": len(train_frame), "validation": len(validation_frame)},
        "selection_uses": "validation_macro_f1_only",
    }
    _write_json(output_validation, result)
    return result


def evaluate_and_select(
    dataset: Path,
    manifest_path: Path,
    models_path: Path,
    validation_path: Path,
    output_model: Path,
    output_evaluation: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    validate_training_manifest(manifest, dataset)
    frame = pd.read_json(dataset, lines=True)
    _, _, test_frame = split_training_frame(frame, manifest)
    validation = json.loads(validation_path.read_text())
    if validation.get("models_sha256") != sha256(models_path):
        raise ValueError("candidate model artifact checksum mismatch")
    metrics = validation.get("validation", {})
    expected_names = set(candidate_models())
    if set(metrics) != expected_names:
        raise ValueError("candidate validation metrics are incomplete")
    selected_name = max(metrics, key=lambda name: (metrics[name]["macro_f1"], name))
    models = joblib.load(models_path)
    if set(models) != expected_names or selected_name not in models:
        raise ValueError("candidate model artifact is invalid")
    selected = models[selected_name]
    test_metrics = evaluate_predictions(
        test_frame["label"], selected.predict(test_frame[list(FEATURE_NAMES)])
    )
    output_model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(selected, output_model)
    result = {
        "warning": "Metrics measure synthetic-proxy prediction, not real cognitive-load accuracy.",
        "contract_version": "1.0",
        "selected_model": selected_name,
        "selection_metric": "validation_macro_f1",
        "selected_validation": metrics[selected_name],
        "test": test_metrics,
        "dataset_sha256": manifest["dataset_sha256"],
        "model_sha256": sha256(output_model),
        "test_count": len(test_frame),
    }
    _write_json(output_evaluation, result)
    return result


def register_candidate(
    dataset_manifest_path: Path,
    model_path: Path,
    evaluation_path: Path,
    output: Path,
    *,
    tracking_uri: str,
    experiment: str,
    model_name: str,
    pipeline_name: str,
    pipeline_run_id: str,
    component_image: str,
) -> dict[str, Any]:
    if not pipeline_name or not pipeline_run_id:
        raise ValueError("KFP pipeline provenance is required")
    if not IMAGE_PATTERN.fullmatch(component_image):
        raise ValueError("component image must use an immutable OCI repository digest")
    manifest = json.loads(dataset_manifest_path.read_text())
    evaluation = json.loads(evaluation_path.read_text())
    if evaluation.get("model_sha256") != sha256(model_path):
        raise ValueError("selected model artifact checksum mismatch")
    if evaluation.get("dataset_sha256") != manifest.get("dataset_sha256"):
        raise ValueError("evaluation dataset lineage mismatch")

    selected = joblib.load(model_path)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    with mlflow.start_run(run_name=f"{pipeline_name}-{pipeline_run_id}") as run:
        mlflow.log_params(
            {
                "model_type": evaluation["selected_model"],
                "dataset_sha256": manifest["dataset_sha256"],
                "git_revision": manifest["git_revision"],
                "feature_schema_version": manifest["feature_schema_version"],
                "label_provenance": manifest["label_provenance"],
                "training_cutoff": manifest["training_cutoff"],
                "kfp_pipeline_name": pipeline_name,
                "kfp_run_id": pipeline_run_id,
                "component_image": component_image,
            }
        )
        mlflow.log_metrics(
            {
                "validation_accuracy": evaluation["selected_validation"]["accuracy"],
                "validation_macro_f1": evaluation["selected_validation"]["macro_f1"],
                "test_accuracy": evaluation["test"]["accuracy"],
                "test_macro_f1": evaluation["test"]["macro_f1"],
            }
        )
        mlflow.log_dict(evaluation, "evaluation.json")
        model_info = mlflow.sklearn.log_model(
            selected,
            artifact_path="model",
            skops_trusted_types=["sklearn.tree._tree.Tree"],
        )
        version = mlflow.register_model(model_info.model_uri, model_name)
        registered_path = Path(mlflow.artifacts.download_artifacts(artifact_uri=version.source))
        artifact_digest = sha256_tree(registered_path)
        client = mlflow.MlflowClient()
        tags = {
            "approval_status": "candidate",
            "registered_artifact_sha256": artifact_digest,
            "dataset_sha256": manifest["dataset_sha256"],
            "git_revision": manifest["git_revision"],
            "feature_schema_version": manifest["feature_schema_version"],
            "label_provenance": manifest["label_provenance"],
            "kfp_pipeline_name": pipeline_name,
            "kfp_run_id": pipeline_run_id,
            "component_image": component_image,
        }
        for key, value in tags.items():
            client.set_model_version_tag(model_name, version.version, key, value)
        observed = client.get_model_version(model_name, version.version)
        if any(observed.tags.get(key) != value for key, value in tags.items()):
            raise RuntimeError("registered model metadata verification failed")
        if sha256_tree(Path(mlflow.artifacts.download_artifacts(artifact_uri=observed.source))) != artifact_digest:
            raise RuntimeError("registered model artifact retrieval verification failed")
        result = {
            "approval_status": "candidate",
            "mlflow_run_id": run.info.run_id,
            "model_name": model_name,
            "model_version": str(version.version),
            "registered_artifact_sha256": artifact_digest,
            **tags,
        }
    _write_json(output, result)
    return result


def record_provenance(
    manifest_path: Path,
    evaluation_path: Path,
    registration_path: Path,
    output: Path,
    *,
    pipeline_name: str,
    pipeline_run_id: str,
    component_image: str,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    evaluation = json.loads(evaluation_path.read_text())
    registration = json.loads(registration_path.read_text())
    expected = {
        "approval_status": "candidate",
        "dataset_sha256": manifest["dataset_sha256"],
        "git_revision": manifest["git_revision"],
        "feature_schema_version": "1.0",
        "label_provenance": "synthetic_proxy",
        "kfp_pipeline_name": pipeline_name,
        "kfp_run_id": pipeline_run_id,
        "component_image": component_image,
    }
    if any(registration.get(key) != value for key, value in expected.items()):
        raise ValueError("registered candidate provenance is incomplete or inconsistent")
    if evaluation.get("dataset_sha256") != manifest["dataset_sha256"]:
        raise ValueError("evaluation provenance is inconsistent")
    result = {
        "contract_version": "1.0",
        "verification": "passed",
        "pipeline_name": pipeline_name,
        "pipeline_run_id": pipeline_run_id,
        "component_image": component_image,
        "dataset_sha256": manifest["dataset_sha256"],
        "splits": manifest["splits"],
        "selected_model": evaluation["selected_model"],
        "mlflow_run_id": registration["mlflow_run_id"],
        "model_name": registration["model_name"],
        "model_version": registration["model_version"],
        "approval_status": "candidate",
        "registered_artifact_sha256": registration["registered_artifact_sha256"],
    }
    _write_json(output, result)
    return result


def main() -> None:  # pragma: no cover - exercised through component commands
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate")
    for name in ("features", "labels", "feature-manifest", "output"):
        validate.add_argument(f"--{name}", type=Path, required=True)
    validate.add_argument("--git-revision", dest="expected_git_revision", required=True)

    prepare = subparsers.add_parser("prepare")
    for name in (
        "features", "labels", "feature-manifest", "validation", "output-dataset", "output-manifest"
    ):
        prepare.add_argument(f"--{name}", type=Path, required=True)
    prepare.add_argument("--training-cutoff", type=datetime.fromisoformat, required=True)
    prepare.add_argument("--git-revision", required=True)

    train = subparsers.add_parser("train")
    for option, destination in (
        ("dataset", "dataset"),
        ("manifest", "manifest_path"),
        ("output-models", "output_models"),
        ("output-validation", "output_validation"),
    ):
        train.add_argument(f"--{option}", dest=destination, type=Path, required=True)

    evaluate = subparsers.add_parser("evaluate")
    for option, destination in (
        ("dataset", "dataset"),
        ("manifest", "manifest_path"),
        ("models", "models_path"),
        ("validation", "validation_path"),
        ("output-model", "output_model"),
        ("output-evaluation", "output_evaluation"),
    ):
        evaluate.add_argument(f"--{option}", dest=destination, type=Path, required=True)

    register = subparsers.add_parser("register")
    for option, destination in (
        ("manifest", "dataset_manifest_path"),
        ("model", "model_path"),
        ("evaluation", "evaluation_path"),
        ("output", "output"),
    ):
        register.add_argument(f"--{option}", dest=destination, type=Path, required=True)
    for name in (
        "tracking-uri", "experiment", "model-name", "pipeline-name", "pipeline-run-id", "component-image"
    ):
        register.add_argument(f"--{name}", required=True)

    provenance = subparsers.add_parser("provenance")
    for option, destination in (
        ("manifest", "manifest_path"),
        ("evaluation", "evaluation_path"),
        ("registration", "registration_path"),
        ("output", "output"),
    ):
        provenance.add_argument(f"--{option}", dest=destination, type=Path, required=True)
    for name in ("pipeline-name", "pipeline-run-id", "component-image"):
        provenance.add_argument(f"--{name}", required=True)

    args = parser.parse_args()
    values = vars(args)
    command = values.pop("command")
    functions = {
        "validate": validate_inputs,
        "prepare": prepare_dataset,
        "train": train_candidates,
        "evaluate": evaluate_and_select,
        "register": register_candidate,
        "provenance": record_provenance,
    }
    print(json.dumps(functions[command](**values)))


if __name__ == "__main__":
    main()
