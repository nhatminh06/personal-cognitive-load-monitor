from __future__ import annotations

import json
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
import pytest

from cogniflow_data.training import candidate_models
from preprocessing_api.features import FEATURE_NAMES
from scripts.train_model import (
    CANDIDATE_ORDER,
    add_features,
    load_dataset,
    select_candidate,
    split_chronologically,
    train,
)


def dataset(*, dates: int = 15) -> pd.DataFrame:
    rows = []
    labels = ("LOW", "MEDIUM", "HIGH")
    for day in range(dates):
        for duplicate_time in range(2):
            rows.append(
                {
                    "date": f"2026-01-{day + 1:02d}",
                    "focus_minutes": 40 + day + duplicate_time,
                    "distraction_minutes": 20 + duplicate_time,
                    "tasks_due": day % 8,
                    "hours_to_deadline": float(120 - day),
                    "cognitive_load_level": labels[day % 3],
                    "label_provenance": "synthetic_proxy",
                }
            )
    return pd.DataFrame(rows)


def write_dataset(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return path


def run_training(tmp_path: Path, frame: pd.DataFrame, *, tracking_uri: str = "") -> dict:
    input_path = write_dataset(tmp_path / "data.csv", frame)
    return train(
        input_path,
        tmp_path / "model.joblib",
        tmp_path / "report.json",
        tmp_path / "train.csv",
        tmp_path / "validation.csv",
        tmp_path / "audit.csv",
        train_fraction=0.6,
        validation_fraction=0.2,
        random_seed=42,
        tracking_uri=tracking_uri,
        experiment_name="module1-test",
    )


def test_timestamp_groups_are_disjoint_chronological_and_deterministic() -> None:
    frame = dataset()
    first = split_chronologically(frame, train_fraction=0.6, validation_fraction=0.2)
    shuffled = frame.sample(frac=1, random_state=9).reset_index(drop=True)
    second = split_chronologically(shuffled, train_fraction=0.6, validation_fraction=0.2)
    for left, right in zip(first[:3], second[:3]):
        assert set(left["date"]) == set(right["date"])
    train_frame, validation_frame, audit_frame, report = first
    assert set(train_frame["date"]).isdisjoint(validation_frame["date"])
    assert set(validation_frame["date"]).isdisjoint(audit_frame["date"])
    assert train_frame["_split_time"].max() < validation_frame["_split_time"].min()
    assert validation_frame["_split_time"].max() < audit_frame["_split_time"].min()
    assert report["duplicate_timestamp_row_count"] == len(frame)
    assert report["final_partition_status"] == "previously_observed_not_independent"
    assert report["partitions"] == second[3]["partitions"]


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True), "duplicate records"),
        (lambda frame: frame.assign(label_provenance="unknown"), "synthetic_proxy"),
        (lambda frame: frame.assign(date="bad"), "valid timestamps"),
    ],
)
def test_invalid_dataset_fails_closed(mutation, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        split_chronologically(
            mutation(dataset()), train_fraction=0.6, validation_fraction=0.2
        )


def test_group_overlap_and_missing_class_fail_closed() -> None:
    overlapping = dataset().assign(session_id="same-session")
    with pytest.raises(ValueError, match="session_id overlaps"):
        split_chronologically(overlapping, train_fraction=0.6, validation_fraction=0.2)

    missing = dataset()
    missing.loc[missing["date"].isin(("2026-01-10", "2026-01-11", "2026-01-12")), "cognitive_load_level"] = "LOW"
    with pytest.raises(ValueError, match="validation partition lacks classes"):
        split_chronologically(missing, train_fraction=0.6, validation_fraction=0.2)


def test_split_configuration_and_missing_input_fail_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="DVC generate_data"):
        load_dataset(tmp_path / "missing.csv")
    with pytest.raises(ValueError, match="leave a previously observed"):
        split_chronologically(dataset(), train_fraction=0.8, validation_fraction=0.2)


def test_selection_uses_metrics_and_declared_tie_order() -> None:
    results = {
        name: {"macro_f1": 0.5, "accuracy": 0.5} for name in CANDIDATE_ORDER
    }
    assert select_candidate(results) == "dummy_majority"
    results["logistic_regression"] = {"macro_f1": 0.6, "accuracy": 0.5}
    results["random_forest"] = {"macro_f1": 0.6, "accuracy": 0.4}
    assert select_candidate(results) == "logistic_regression"


def test_preprocessing_is_fitted_on_training_only() -> None:
    train_raw, validation_raw, _, _ = split_chronologically(
        dataset(), train_fraction=0.6, validation_fraction=0.2
    )
    train_frame, validation_frame = add_features(train_raw), add_features(validation_raw)
    logistic = candidate_models(42)["logistic_regression"]
    logistic.fit(train_frame[list(FEATURE_NAMES)], train_frame["cognitive_load_level"])
    scaler = logistic.named_steps["scaler"]
    assert scaler.mean_ == pytest.approx(train_frame[list(FEATURE_NAMES)].mean().to_numpy())
    assert not np.allclose(
        scaler.mean_,
        pd.concat([train_frame, validation_frame])[list(FEATURE_NAMES)].mean().to_numpy(),
    )


def test_audit_partition_cannot_change_selection_or_validation(tmp_path: Path) -> None:
    frame = dataset()
    first = run_training(tmp_path / "first", frame)
    changed = frame.copy()
    audit_dates = {f"2026-01-{day:02d}" for day in range(13, 16)}
    mask = changed["date"].isin(audit_dates)
    changed.loc[mask, "cognitive_load_level"] = ["HIGH", "HIGH", "MEDIUM", "MEDIUM", "LOW", "LOW"]
    second = run_training(tmp_path / "second", changed)
    assert first["selected_model"] == second["selected_model"]
    assert first["models"] == second["models"]
    assert first["split"]["partitions"]["train"] == second["split"]["partitions"]["train"]
    assert first["split"]["partitions"]["validation"] == second["split"]["partitions"]["validation"]


def test_exported_candidate_matches_validation_predictions(tmp_path: Path) -> None:
    report = run_training(tmp_path, dataset())
    model = joblib.load(tmp_path / "model.joblib")
    validation = pd.read_csv(tmp_path / "validation.csv")
    predictions = model.predict(validation[list(FEATURE_NAMES)])
    assert len(predictions) == len(validation)
    assert report["selected_model"] in CANDIDATE_ORDER
    assert report["previously_observed_audit"]["status"] == (
        "not_independent_and_not_used_for_selection"
    )
    assert "rule_baseline" not in report["models"]


def test_training_repeats_metrics_predictions_and_model_bytes(tmp_path: Path) -> None:
    frame = dataset()
    first = run_training(tmp_path / "first", frame)
    second = run_training(tmp_path / "second", frame.sample(frac=1, random_state=9))
    first_model = tmp_path / "first/model.joblib"
    second_model = tmp_path / "second/model.joblib"
    validation = pd.read_csv(tmp_path / "first/validation.csv")

    assert first["selected_model"] == second["selected_model"]
    assert first["models"] == second["models"]
    assert first["exported_joblib_sha256"] == second["exported_joblib_sha256"]
    assert first_model.read_bytes() == second_model.read_bytes()
    assert joblib.load(first_model).predict(validation[list(FEATURE_NAMES)]).tolist() == (
        joblib.load(second_model).predict(validation[list(FEATURE_NAMES)]).tolist()
    )


def test_mlflow_is_isolated_and_records_lineage_without_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    report = run_training(tmp_path, dataset(), tracking_uri=tracking_uri)
    client = mlflow.MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name("module1-test")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == len(CANDIDATE_ORDER)
    assert not client.search_registered_models()
    for run in runs:
        assert run.data.params["feature_schema_version"] == "1.0"
        assert run.data.params["validation_scope"] == "synthetic_proxy_engineering_only"
        assert len(run.data.params["split_sha256"]) == 64
        assert "validation_macro_f1" in run.data.metrics
    assert report["registry_mutation"] == "none"
    assert json.loads((tmp_path / "report.json").read_text())["selected_model"] == report["selected_model"]
