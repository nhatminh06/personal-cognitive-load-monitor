"""Reproducible focus-session dataset and A/B/C experiment tests."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import joblib
import mlflow
import pandas as pd
import pytest
from pydantic import ValidationError

from cogniflow_contracts import SessionLifecycleEvent
from cogniflow_data.multimodal import (
    BEHAVIORAL_FEATURES,
    CV_FEATURES,
    MULTIMODAL_FEATURES,
    MultimodalDatasetRow,
    build_dataset_rows,
    build_split_manifest,
    load_dataset,
    run_experiments,
    sha256_file,
    synthetic_snapshot,
    write_dataset_bundle,
)
from cogniflow_sessions import FocusSessionRepository


def bundle(tmp_path: Path, snapshot: dict | None = None):
    paths = (tmp_path / "dataset.jsonl", tmp_path / "manifest.json", tmp_path / "splits.json")
    manifest, splits = write_dataset_bundle(
        snapshot or synthetic_snapshot(), *paths, git_revision="a" * 40,
        random_seed=42, data_provenance="synthetic_pipeline_fixture",
    )
    return (*paths, manifest, splits)


def test_exact_join_corrections_missing_cv_and_microseconds(tmp_path):
    dataset, _, _, manifest, splits = bundle(tmp_path)
    rows = load_dataset(dataset)
    assert len(rows) == 90 and manifest["valid_label_count"] == 90
    assert rows[0].self_reported_effort == 2  # deterministic latest correction
    assert rows[0].window_start.microsecond == 123456
    assert rows[0].feature_cutoff == rows[0].window_end
    assert any(row.cv_available == 0 and row.face_presence_ratio is None for row in rows)
    assert any(row.cv_available == 1 and row.face_presence_ratio is not None for row in rows)
    assert manifest["paired_cv_count"] + manifest["missing_cv_count"] == 90
    assert splits["status"] == "PASS"
    assert manifest["target"] == "self_reported_effort"


def test_dataset_and_split_digests_are_reproducible_and_ingestion_order_independent(tmp_path):
    snapshot = synthetic_snapshot()
    first = bundle(tmp_path / "one", snapshot)
    reordered = dict(snapshot)
    for name in ("windows", "lifecycle", "activity", "cv", "labels"):
        reordered[name] = list(reversed(snapshot[name]))
    second = bundle(tmp_path / "two", reordered)
    assert first[3]["dataset_sha256"] == second[3]["dataset_sha256"]
    assert first[3]["source_snapshot_sha256"] == second[3]["source_snapshot_sha256"]
    assert first[3]["split_manifest_sha256"] == second[3]["split_manifest_sha256"]


def test_snapshot_cutoff_wrong_schema_duplicates_and_private_fields_fail_closed():
    future = synthetic_snapshot()
    future["activity"][0]["ingested_at"] = (
        datetime.fromisoformat(future["snapshot_cutoff"]) + timedelta(microseconds=1)
    ).isoformat()
    with pytest.raises(ValueError, match="ingested after"):
        build_dataset_rows(future)

    wrong_schema = synthetic_snapshot()
    wrong_schema["activity"][0]["schema_version"] = "2.0"
    with pytest.raises(ValidationError):
        build_dataset_rows(wrong_schema)

    private = synthetic_snapshot()
    private["activity"][0]["window_title"] = "private.py"
    with pytest.raises(ValidationError):
        build_dataset_rows(private)

    duplicate = synthetic_snapshot()
    duplicate["activity"].append(dict(duplicate["activity"][0]))
    with pytest.raises(ValueError, match="duplicate behavioral"):
        build_dataset_rows(duplicate)

    conflict = synthetic_snapshot()
    changed = dict(conflict["activity"][0])
    changed["event_id"] = str(uuid4())
    changed["active_seconds"] -= 1
    changed["idle_seconds"] += 1
    conflict["activity"].append(changed)
    with pytest.raises(ValueError, match="conflicting behavioral"):
        build_dataset_rows(conflict)


def test_grouped_chronological_splits_are_disjoint_and_insufficient_is_explicit(tmp_path):
    dataset, _, _, _, splits = bundle(tmp_path)
    rows = load_dataset(dataset)
    split_sets = [set(splits["splits"][name]) for name in ("train", "validation", "test")]
    assert not split_sets[0] & split_sets[1]
    assert not split_sets[0] & split_sets[2]
    assert not split_sets[1] & split_sets[2]
    by_id = {str(row.window_id): row for row in rows}
    assert max(by_id[item].window_end for item in split_sets[0]) <= min(
        by_id[item].window_start for item in split_sets[1]
    )
    assert splits["group_field"] == "session_key" and splits["population_scope"] == "within_subject"
    insufficient = build_split_manifest(rows[:89], sha256_file(dataset), random_seed=42)
    assert insufficient["status"] == "INSUFFICIENT_DATA"
    assert "at least 90" in insufficient["reasons"][0]


def test_two_subjects_do_not_fall_back_to_row_splitting(tmp_path):
    dataset, _, _, _, _ = bundle(tmp_path)
    rows = load_dataset(dataset)
    changed = [
        row.model_copy(update={"subject_key": hashlib.sha256(
            ("subject-a" if index < 45 else "subject-b").encode()
        ).hexdigest()})
        for index, row in enumerate(rows)
    ]
    result = build_split_manifest(changed, sha256_file(dataset), random_seed=42)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert "two subjects" in result["reasons"][0]


def test_training_is_cpu_only_train_fitted_and_same_cohort(tmp_path):
    dataset, manifest_path, splits_path, manifest, _ = bundle(tmp_path)
    report = run_experiments(
        dataset, manifest_path, splits_path, tmp_path / "models", tmp_path / "report.json",
        tracking_uri=f"sqlite:///{tmp_path / 'mlflow.db'}", experiment_name="multimodal-test",
        validation_scope="engineering_validation",
    )
    assert report["status"] == "PASS" and report["models_registered"] == 0
    assert set(report["experiments"]) == {"A", "B", "C"}
    assert report["experiments"]["A"]["feature_names"] == list(BEHAVIORAL_FEATURES)
    assert report["experiments"]["B"]["feature_names"] == list(CV_FEATURES)
    assert report["experiments"]["C"]["feature_names"] == list(MULTIMODAL_FEATURES)
    paired = report["paired_cv_present_evaluation"]
    assert paired["status"] == "PASS"
    assert len({paired["metrics"][name]["sample_count"] for name in ("A", "B", "C")}) == 1
    assert all(1 <= report["experiments"][name]["test"]["prediction_min"] <= 7
               for name in ("A", "B", "C"))
    assert "cv2" not in sys.modules and "mediapipe" not in sys.modules

    frame = pd.read_json(dataset, lines=True)
    split = json.loads(splits_path.read_text())
    train = frame[frame["window_id"].isin(split["splits"]["train"])]
    model = joblib.load(tmp_path / "models" / "experiment-C.joblib")
    imputer = model.named_steps["imputer"]
    build_index = list(MULTIMODAL_FEATURES).index("build_count")
    assert imputer.statistics_[build_index] == pytest.approx(train["build_count"].median())
    assert manifest["data_provenance"] == "synthetic_pipeline_fixture"


def test_mlflow_runs_are_candidate_only_and_synthetic_registration_is_blocked(tmp_path):
    dataset, manifest, splits, _, _ = bundle(tmp_path)
    tracking_uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    report = run_experiments(
        dataset, manifest, splits, tmp_path / "models", tmp_path / "report.json",
        tracking_uri=tracking_uri, experiment_name="candidate-only",
        validation_scope="engineering_validation",
    )
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.MlflowClient()
    for details in report["mlflow"].values():
        run = client.get_run(details["mlflow_run_id"])
        assert run.data.tags["approval_status"] == "candidate"
        assert run.data.tags["validation_scope"] == "engineering_validation"
    assert client.search_registered_models() == []
    with pytest.raises(ValueError, match="synthetic engineering candidates cannot be registered"):
        run_experiments(
            dataset, manifest, splits, tmp_path / "registered-models",
            tmp_path / "registered-report.json", tracking_uri=tracking_uri,
            experiment_name="registration-block", validation_scope="engineering_validation",
            register_candidates=True,
        )


def test_repository_snapshot_is_owner_scoped_cutoff_bounded_and_excludes_cancelled(tmp_path):
    repository = FocusSessionRepository(tmp_path / "sessions.sqlite3")
    owner, other = "owner-a", "owner-b"
    start = datetime(2026, 1, 1, 12, 0, 0, 654321, tzinfo=UTC)

    def lifecycle(session_id: str, event_type: str, sequence: int, when: datetime):
        return SessionLifecycleEvent(
            session_id=session_id, event_time=when, ingested_at=when,
            source="test", producer_version="1.0.0", idempotency_key=f"{session_id}:{sequence}",
            event_type=event_type, sequence=sequence, session_kind="study", privacy_mode="behavioral",
        )

    repository.create(lifecycle("owned", "session.started", 1, start), owner)
    repository.transition(lifecycle("owned", "session.completed", 2, start + timedelta(minutes=6)), owner)
    repository.create(lifecycle("cancelled", "session.started", 1, start), owner)
    repository.transition(lifecycle("cancelled", "session.cancelled", 2, start + timedelta(minutes=6)), owner)
    repository.create(lifecycle("other", "session.started", 1, start), other)
    snapshot = repository.experiment_snapshot(owner, start + timedelta(minutes=7))
    assert [item["session_id"] for item in snapshot["sessions"]] == ["owned"]
    assert snapshot["windows"][0]["window_start"].endswith(".654321+00:00")
    with pytest.raises(ValueError, match="timezone"):
        repository.experiment_snapshot(owner, datetime(2026, 1, 1))


def test_dataset_row_rejects_private_and_fabricated_cv_fields(tmp_path):
    dataset, _, _, _, _ = bundle(tmp_path)
    payload = json.loads(dataset.read_text().splitlines()[0])
    payload["window_title"] = "secret"
    with pytest.raises(ValidationError):
        MultimodalDatasetRow.model_validate(payload)
    payload.pop("window_title")
    payload["cv_available"] = 0
    payload["face_presence_ratio"] = 0.0
    with pytest.raises(ValidationError, match="must remain null"):
        MultimodalDatasetRow.model_validate(payload)
