from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cogniflow_data.kfp_tasks import (
    evaluate_and_select,
    prepare_dataset,
    record_provenance,
    register_candidate,
    train_candidates,
    validate_inputs,
)
from scripts.generate_training_fixture import generate_fixture

GIT_REVISION = "a" * 40
IMAGE = "localhost/cogniflow-kfp@sha256:" + "b" * 64
CUTOFF = datetime(2026, 2, 1, tzinfo=UTC)


def fixture(tmp_path: Path):
    features = tmp_path / "features.jsonl"
    labels = tmp_path / "labels.jsonl"
    feature_manifest = tmp_path / "feature-manifest.json"
    generate_fixture(features, labels, feature_manifest, 180)
    return features, labels, feature_manifest


def prepared(tmp_path: Path):
    features, labels, feature_manifest = fixture(tmp_path)
    validation = tmp_path / "validation.json"
    validate_inputs(
        features, labels, feature_manifest, validation, expected_git_revision=GIT_REVISION
    )
    dataset, manifest = tmp_path / "dataset.jsonl", tmp_path / "manifest.json"
    prepare_dataset(
        features,
        labels,
        feature_manifest,
        validation,
        dataset,
        manifest,
        training_cutoff=CUTOFF,
        git_revision=GIT_REVISION,
    )
    return dataset, manifest


def evaluated(tmp_path: Path):
    dataset, manifest = prepared(tmp_path)
    models, validation = tmp_path / "models.joblib", tmp_path / "validation-metrics.json"
    train_report = train_candidates(dataset, manifest, models, validation)
    assert train_report["split_counts"] == {"train": 108, "validation": 36}
    selected, evaluation = tmp_path / "selected.joblib", tmp_path / "evaluation.json"
    evaluate_report = evaluate_and_select(
        dataset, manifest, models, validation, selected, evaluation
    )
    assert evaluate_report["test_count"] == 36
    return manifest, selected, evaluation


def test_kfp_tasks_preserve_180_row_contract_and_candidate_registration(tmp_path: Path) -> None:
    manifest, selected, evaluation = evaluated(tmp_path)
    registration = tmp_path / "registration.json"
    result = register_candidate(
        manifest,
        selected,
        evaluation,
        registration,
        tracking_uri=f"sqlite:///{tmp_path / 'mlflow.db'}",
        experiment="kfp-test",
        model_name="kfp-test-model",
        pipeline_name="cogniflow-kubeflow-training",
        pipeline_run_id="run-123",
        component_image=IMAGE,
    )
    assert result["approval_status"] == "candidate"
    assert len(result["registered_artifact_sha256"]) == 64
    provenance = record_provenance(
        manifest,
        evaluation,
        registration,
        tmp_path / "provenance.json",
        pipeline_name="cogniflow-kubeflow-training",
        pipeline_run_id="run-123",
        component_image=IMAGE,
    )
    assert provenance["verification"] == "passed"
    assert provenance["splits"] == {
        "train": [0, 108], "validation": [108, 144], "test": [144, 180]
    }


def test_validation_checksum_schema_and_image_revision_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    features, labels, feature_manifest = fixture(tmp_path)
    features.write_text(features.read_text() + " ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_inputs(features, labels, feature_manifest, tmp_path / "out", expected_git_revision=GIT_REVISION)

    features, labels, feature_manifest = fixture(tmp_path)
    metadata = json.loads(feature_manifest.read_text())
    metadata["feature_schema_version"] = "2.0"
    feature_manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="unsupported feature manifest"):
        validate_inputs(features, labels, feature_manifest, tmp_path / "out", expected_git_revision=GIT_REVISION)

    monkeypatch.setenv("COGNIFLOW_CODE_REVISION", "b" * 40)
    features, labels, feature_manifest = fixture(tmp_path)
    with pytest.raises(ValueError, match="code revision mismatch"):
        validate_inputs(features, labels, feature_manifest, tmp_path / "out", expected_git_revision=GIT_REVISION)


def test_tampered_model_and_missing_provenance_fail_closed(tmp_path: Path) -> None:
    manifest, selected, evaluation = evaluated(tmp_path)
    selected.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="model artifact checksum mismatch"):
        register_candidate(
            manifest,
            selected,
            evaluation,
            tmp_path / "registration.json",
            tracking_uri="sqlite:///:memory:",
            experiment="test",
            model_name="test",
            pipeline_name="pipeline",
            pipeline_run_id="run",
            component_image=IMAGE,
        )

    registration = tmp_path / "registration.json"
    registration.write_text(json.dumps({"approval_status": "candidate"}))
    with pytest.raises(ValueError, match="provenance is incomplete"):
        record_provenance(
            manifest,
            evaluation,
            registration,
            tmp_path / "out.json",
            pipeline_name="pipeline",
            pipeline_run_id="run",
            component_image=IMAGE,
        )


def test_mlflow_failure_propagates_without_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, selected, evaluation = evaluated(tmp_path)
    monkeypatch.setattr(
        "cogniflow_data.kfp_tasks.mlflow.set_tracking_uri",
        lambda _: (_ for _ in ()).throw(RuntimeError("MLflow unavailable")),
    )
    output = tmp_path / "registration.json"
    with pytest.raises(RuntimeError, match="MLflow unavailable"):
        register_candidate(
            manifest,
            selected,
            evaluation,
            output,
            tracking_uri="broken",
            experiment="test",
            model_name="test",
            pipeline_name="pipeline",
            pipeline_run_id="run",
            component_image=IMAGE,
        )
    assert not output.exists()
