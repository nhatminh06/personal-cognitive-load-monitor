"""Real serialization and parity tests for the synthetic Module I package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
import skops.io
from sklearn.ensemble import RandomForestClassifier

from cogniflow_kserve.engineering import (
    TRUSTED_TYPES,
    package_engineering_model,
    validated_engineering_manifest,
)
from cogniflow_kserve.predictor import CogniFlowPredictor
from preprocessing_api.features import FEATURE_NAMES


def _source(tmp_path: Path) -> tuple[Path, Path, Path]:
    rows = pd.DataFrame(
        [
            [0, 0, 0, 87600, 0, 0],
            [1440, 0, 0, 0, 1, 0],
            [0, 1440, 1000, 0, 0, 1],
            [120, 30, 3, 24, 0.8, 0.2],
            [30, 120, 8, 4, 0.2, 0.8],
            [60, 60, 2, 48, 0.5, 0.5],
        ],
        columns=FEATURE_NAMES,
    )
    labels = ["LOW", "LOW", "HIGH", "MEDIUM", "HIGH", "MEDIUM"]
    model = RandomForestClassifier(n_estimators=8, random_state=42).fit(rows, labels)
    source = tmp_path / "model.joblib"
    joblib.dump(model, source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    validation = tmp_path / "validation.csv"
    rows.assign(cognitive_load_level=labels).to_csv(validation, index=False)
    report = tmp_path / "metrics.json"
    report.write_text(
        json.dumps(
            {
                "contract_version": "2.0",
                "selected_model": "random_forest",
                "validation_scope": "synthetic_proxy_engineering_only",
                "exported_joblib_sha256": digest,
                "mlflow": {
                    "experiment": "cogniflow-module1-engineering-candidates",
                    "candidate_run_ids": {
                        "dummy_majority": "b" * 32,
                        "logistic_regression": "c" * 32,
                        "random_forest": "a" * 32,
                    },
                    "selected_run_id": "a" * 32,
                },
                "lineage": {
                    "dataset_sha256": "a" * 64,
                    "git_revision": "b" * 40,
                    "feature_schema_version": "1.0",
                    "feature_names": list(FEATURE_NAMES),
                    "label_provenance": "synthetic_proxy",
                },
            }
        )
    )
    return source, report, validation


def _environment(monkeypatch: pytest.MonkeyPatch, package: Path, manifest: dict) -> None:
    values = {
        "MODEL_PATH": str(package / "cognitive_load_model.skops"),
        "MODEL_PACKAGE_PATH": str(package / "model-package.json"),
        "MODEL_NAME": manifest["model_name"],
        "MODEL_VERSION": manifest["model_version"],
        "MODEL_ARTIFACT_SHA256": manifest["registered_artifact_sha256"],
        "MODEL_SHA256": manifest["packaged_model_sha256"],
        "MODEL_DATASET_SHA256": manifest["dataset_sha256"],
        "MODEL_FEATURE_SCHEMA_VERSION": manifest["feature_schema_version"],
    }
    for name, value in values.items():
        monkeypatch.setenv(name, str(value))


def test_real_package_and_predictor_match_offline_model(monkeypatch, tmp_path):
    source, report, validation = _source(tmp_path)
    package = tmp_path / "package"
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = package_engineering_model(
        source,
        report,
        validation,
        package,
        expected_source_sha256=source_digest,
    )
    assert manifest["approval_status"] == "engineering_fixture"
    assert manifest["engineering_mlflow_run_id"] == "a" * 32
    assert manifest["approved_by"] is None
    assert skops.io.get_untrusted_types(
        file=package / "cognitive_load_model.skops"
    ) == TRUSTED_TYPES

    _environment(monkeypatch, package, manifest)
    predictor = CogniFlowPredictor(manifest_validator=validated_engineering_manifest)
    assert predictor.load() is True
    frame = pd.read_csv(validation)
    instances = frame[list(FEATURE_NAMES)].values.tolist()
    offline = joblib.load(source)
    result = predictor.predict(
        {"feature_names": list(FEATURE_NAMES), "instances": instances}
    )
    assert result["predictions"] == offline.predict(frame[list(FEATURE_NAMES)]).tolist()


def test_packaging_rejects_digest_report_and_unexpected_types(monkeypatch, tmp_path):
    source, report, validation = _source(tmp_path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="source digest"):
        package_engineering_model(
            source, report, validation, tmp_path / "digest", expected_source_sha256="0" * 64
        )

    payload = json.loads(report.read_text())
    payload["mlflow"]["selected_run_id"] = "d" * 32
    report.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="report is incompatible"):
        package_engineering_model(
            source, report, validation, tmp_path / "lineage", expected_source_sha256=digest
        )

    payload["mlflow"]["selected_run_id"] = "a" * 32
    payload["lineage"]["feature_names"] = ["wrong"]
    report.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="report is incompatible"):
        package_engineering_model(
            source, report, validation, tmp_path / "report", expected_source_sha256=digest
        )

    payload["lineage"]["feature_names"] = list(FEATURE_NAMES)
    report.write_text(json.dumps(payload))
    monkeypatch.setattr(
        "skops.io.get_untrusted_types", lambda **kwargs: ["unexpected.Type"]
    )
    with pytest.raises(ValueError, match="unexpected serialized types"):
        package_engineering_model(
            source, report, validation, tmp_path / "types", expected_source_sha256=digest
        )


def test_engineering_manifest_rejects_corruption_and_production_validator(
    monkeypatch, tmp_path
):
    from preprocessing_api.model_client import validated_package_manifest

    source, report, validation = _source(tmp_path)
    package = tmp_path / "package"
    manifest = package_engineering_model(
        source,
        report,
        validation,
        package,
        expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    _environment(monkeypatch, package, manifest)
    model = package / "cognitive_load_model.skops"
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    assert validated_engineering_manifest(model, digest) == manifest
    with pytest.raises(ValueError):
        validated_package_manifest(model, digest)

    model.chmod(0o644)
    model.write_bytes(model.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="manifest contract is invalid"):
        validated_engineering_manifest(model, hashlib.sha256(model.read_bytes()).hexdigest())
