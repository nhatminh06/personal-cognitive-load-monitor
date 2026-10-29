"""Synthetic-only Module I package support for local integration tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import skops.io
from sklearn.ensemble import RandomForestClassifier

from preprocessing_api.features import FEATURE_NAMES

TRUSTED_TYPES = ["sklearn.tree._tree.Tree"]
ENGINEERING_CANDIDATES = {"dummy_majority", "logistic_regression", "random_forest"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_model(model: Any) -> None:
    if (
        not isinstance(model, RandomForestClassifier)
        or model.n_features_in_ != len(FEATURE_NAMES)
        or list(model.feature_names_in_) != list(FEATURE_NAMES)
        or set(model.classes_) != {"LOW", "MEDIUM", "HIGH"}
    ):
        raise ValueError("engineering model contract is incompatible")


def package_engineering_model(
    source_model: Path,
    report_path: Path,
    validation_path: Path,
    output_dir: Path,
    *,
    expected_source_sha256: str,
) -> dict[str, Any]:
    """Convert one digest-bound 2B joblib into a synthetic-only skops package."""

    if not re.fullmatch(r"[a-f0-9]{64}", expected_source_sha256):
        raise ValueError("expected source digest must be a lowercase SHA-256")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    if not source_model.is_file() or source_model.suffix != ".joblib":
        raise ValueError("engineering source must be a joblib artifact")
    source_digest = _sha256(source_model)
    if not hmac.compare_digest(source_digest, expected_source_sha256):
        raise ValueError("engineering source digest does not match")

    report = json.loads(report_path.read_text())
    lineage = report.get("lineage", {})
    mlflow = report.get("mlflow", {})
    candidate_run_ids = mlflow.get("candidate_run_ids", {})
    if (
        report.get("contract_version") != "2.0"
        or report.get("selected_model") != "random_forest"
        or report.get("validation_scope") != "synthetic_proxy_engineering_only"
        or report.get("exported_joblib_sha256") != source_digest
        or mlflow.get("experiment") != "cogniflow-module1-engineering-candidates"
        or not isinstance(candidate_run_ids, dict)
        or set(candidate_run_ids) != ENGINEERING_CANDIDATES
        or any(
            not re.fullmatch(r"[a-f0-9]{32}", str(value))
            for value in candidate_run_ids.values()
        )
        or mlflow.get("selected_run_id")
        != candidate_run_ids.get(report.get("selected_model"))
        or lineage.get("feature_schema_version") != "1.0"
        or lineage.get("feature_names") != list(FEATURE_NAMES)
        or lineage.get("label_provenance") != "synthetic_proxy"
        or not re.fullmatch(r"[a-f0-9]{64}", str(lineage.get("dataset_sha256", "")))
        or not re.fullmatch(r"[a-f0-9]{40}", str(lineage.get("git_revision", "")))
    ):
        raise ValueError("engineering evaluation report is incompatible")

    model = joblib.load(source_model)
    _validate_model(model)
    validation = pd.read_csv(validation_path)
    if list(validation.columns[: len(FEATURE_NAMES)]) != list(FEATURE_NAMES):
        raise ValueError("validation feature order is incompatible")
    features = validation[list(FEATURE_NAMES)]
    offline_predictions = model.predict(features)
    offline_probabilities = model.predict_proba(features)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_dir.parent) as temporary:
        package = Path(temporary) / output_dir.name
        package.mkdir()
        packaged_model = package / "cognitive_load_model.skops"
        skops.io.dump(model, packaged_model)
        if skops.io.get_untrusted_types(file=packaged_model) != TRUSTED_TYPES:
            raise ValueError("engineering package contains unexpected serialized types")
        loaded = skops.io.load(packaged_model, trusted=TRUSTED_TYPES)
        _validate_model(loaded)
        if list(loaded.predict(features)) != list(offline_predictions):
            raise ValueError("packaged prediction parity failed")
        if not (loaded.predict_proba(features) == offline_probabilities).all():
            raise ValueError("packaged probability parity failed")

        packaged_digest = _sha256(packaged_model)
        manifest: dict[str, Any] = {
            "contract_version": "1.0",
            "package_scope": "synthetic_engineering_test",
            "validation_scope": "synthetic_proxy_engineering_only",
            "approval_status": "engineering_fixture",
            "model_name": "cognitive-load-engineering",
            "model_version": "engineering-2b",
            "run_id": "not-registered",
            "engineering_mlflow_run_id": mlflow["selected_run_id"],
            "registered_source": "local-dvc:models/cognitive_load_model.joblib",
            "registered_artifact_sha256": source_digest,
            "source_model_sha256": source_digest,
            "packaged_model_sha256": packaged_digest,
            "evaluation_report_sha256": _sha256(report_path),
            "dataset_sha256": lineage["dataset_sha256"],
            "feature_schema_version": "1.0",
            "feature_names": list(FEATURE_NAMES),
            "label_provenance": "synthetic_proxy",
            "git_revision": lineage["git_revision"],
            "approved_by": None,
            "approved_at": None,
        }
        manifest_path = package / "model-package.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        packaged_model.chmod(0o444)
        manifest_path.chmod(0o444)
        package.rename(output_dir)
    return manifest


def validated_engineering_manifest(model_path: Path, actual_digest: str) -> dict[str, Any]:
    """Validate a synthetic package; production callers never use this function."""

    manifest_path = Path(os.getenv("MODEL_PACKAGE_PATH", model_path.with_name("model-package.json")))
    manifest = json.loads(manifest_path.read_text())
    expected = {
        "model_name": os.getenv("MODEL_NAME", ""),
        "model_version": os.getenv("MODEL_VERSION", ""),
        "registered_artifact_sha256": os.getenv("MODEL_ARTIFACT_SHA256", ""),
        "dataset_sha256": os.getenv("MODEL_DATASET_SHA256", ""),
        "feature_schema_version": os.getenv("MODEL_FEATURE_SCHEMA_VERSION", ""),
        "packaged_model_sha256": os.getenv("MODEL_SHA256", ""),
    }
    if any(not value or str(manifest.get(name, "")) != value for name, value in expected.items()):
        raise ValueError("engineering package does not match serving configuration")
    if (
        manifest.get("contract_version") != "1.0"
        or manifest.get("package_scope") != "synthetic_engineering_test"
        or manifest.get("validation_scope") != "synthetic_proxy_engineering_only"
        or manifest.get("approval_status") != "engineering_fixture"
        or manifest.get("model_name") != "cognitive-load-engineering"
        or manifest.get("model_version") != "engineering-2b"
        or manifest.get("run_id") != "not-registered"
        or not re.fullmatch(
            r"[a-f0-9]{32}", str(manifest.get("engineering_mlflow_run_id", ""))
        )
        or manifest.get("registered_source") != "local-dvc:models/cognitive_load_model.joblib"
        or manifest.get("feature_names") != list(FEATURE_NAMES)
        or manifest.get("label_provenance") != "synthetic_proxy"
        or manifest.get("approved_by") is not None
        or manifest.get("approved_at") is not None
        or manifest.get("source_model_sha256") != manifest.get("registered_artifact_sha256")
        or not hmac.compare_digest(str(manifest.get("packaged_model_sha256", "")), actual_digest)
    ):
        raise ValueError("engineering package manifest contract is invalid")
    return manifest
