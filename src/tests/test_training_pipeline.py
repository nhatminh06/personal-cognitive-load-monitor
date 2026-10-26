from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cogniflow_data.historical import HistoricalFeatureRow, SyntheticLabel, SYNTHETIC_DATASET
from cogniflow_data.training import prepare_training_dataset
from preprocessing_api.features import FEATURE_NAMES
from scripts.train_historical_model import train


def training_files(tmp_path: Path, *, labels: tuple[str, ...] = ("LOW", "MEDIUM", "HIGH")):
    rows = []
    for index in range(90):
        label = labels[index % len(labels)]
        focus, distraction = index % 11 + 1, index % 7 + 1
        total = focus + distraction
        rows.append(
            {
                "decision_id": f"d{index:03d}",
                "decision_time": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index)).isoformat(),
                "feature_available_at": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index, minutes=-1)).isoformat(),
                "label_event_time": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index)).isoformat(),
                "label_available_at": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index, minutes=1)).isoformat(),
                "focus_minutes": focus,
                "distraction_minutes": distraction,
                "tasks_due": index % 11,
                "hours_to_deadline": float(index % 11),
                "focus_ratio": focus / total,
                "distraction_ratio": distraction / total,
                "label": label,
                "label_provenance": "synthetic_proxy",
            }
        )
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("".join(json.dumps(row) + "\n" for row in rows))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_version": "1.0",
                "dataset_id": "test-training-dataset",
                "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "feature_input_sha256": "1" * 64,
                "label_input_sha256": "2" * 64,
                "feature_schema_version": "1.0",
                "feature_names": list(FEATURE_NAMES),
                "source_dataset": SYNTHETIC_DATASET,
                "source_delta_versions": [],
                "git_revision": "a" * 40,
                "training_cutoff": "2026-01-15T00:00:00+00:00",
                "label_availability_cutoff": "2026-01-15T00:00:00+00:00",
                "label_provenance": "synthetic_proxy",
                "sample_count": 90,
                "validation": "passed",
                "splits": {"train": [0, 54], "validation": [54, 72], "test": [72, 90]},
            }
        )
    )
    return dataset, manifest


def files(tmp_path: Path, *, label_delay: int = 1):
    decision = datetime(2026, 1, 1, tzinfo=UTC)
    feature = HistoricalFeatureRow(
        decision_id="d1", session_id="s1", event_id="00000000-0000-0000-0000-000000000001",
        feature_schema_version="1.0", decision_time=decision, event_time=decision-timedelta(minutes=2),
        ingested_at=decision-timedelta(minutes=1), available_at=decision-timedelta(minutes=1),
        source_dataset=SYNTHETIC_DATASET, source="test", kafka_topic="test", kafka_partition=0,
        kafka_offset=0, focus_minutes=90, distraction_minutes=30, tasks_due=2,
        hours_to_deadline=24, focus_ratio=.75, distraction_ratio=.25,
    )
    label = SyntheticLabel(decision_id="d1", label="MEDIUM", event_time=decision, available_at=decision+timedelta(days=label_delay))
    feature_path, label_path, manifest_path = tmp_path/"features.jsonl", tmp_path/"labels.jsonl", tmp_path/"features.json"
    feature_path.write_text(feature.model_dump_json()+"\n")
    label_path.write_text(label.model_dump_json()+"\n")
    import hashlib
    manifest_path.write_text(json.dumps({"sha256":hashlib.sha256(feature_path.read_bytes()).hexdigest(),"feature_schema_version":"1.0","feature_names":list(FEATURE_NAMES),"source_dataset":SYNTHETIC_DATASET,"source_delta_versions":[]}))
    return feature_path, manifest_path, label_path


def prepare(tmp_path, **kwargs):
    paths = files(tmp_path, **kwargs)
    return prepare_training_dataset(*paths, tmp_path/"dataset.jsonl", tmp_path/"manifest.json", training_cutoff=datetime(2026,1,3,tzinfo=UTC), git_revision="a" * 40)


def test_join_preserves_temporal_and_lineage_contract(tmp_path):
    result = prepare(tmp_path)
    assert result["sample_count"] == 1
    assert result["source_delta_versions"] == []
    assert result["git_revision"] == "a" * 40


def test_late_label_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="unavailable by cutoff"):
        prepare(tmp_path, label_delay=4)


def test_duplicate_and_missing_labels_fail_closed(tmp_path):
    features, manifest, labels = files(tmp_path)
    labels.write_text(labels.read_text()*2)
    with pytest.raises(ValueError, match="duplicate label"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="a" * 40)
    labels.write_text("")
    with pytest.raises(ValueError, match="missing label"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="a" * 40)


def test_manifest_tampering_and_future_feature_fail_closed(tmp_path):
    features, manifest, labels = files(tmp_path)
    features.write_text(features.read_text()+" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="a" * 40)

    feature = json.loads(features.read_text())
    feature["available_at"] = "2026-01-01T01:00:00Z"
    features.write_text(json.dumps(feature) + "\n")
    feature_manifest = json.loads(manifest.read_text())
    feature_manifest["sha256"] = hashlib.sha256(features.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(feature_manifest))
    with pytest.raises(ValueError, match="point-in-time ordering"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="a" * 40)


@pytest.mark.parametrize("field,value", [("feature_schema_version", "2.0"), ("feature_names", list(reversed(FEATURE_NAMES)))])
def test_feature_manifest_contract_fails_closed(tmp_path, field, value):
    features, manifest, labels = files(tmp_path)
    feature_manifest = json.loads(manifest.read_text())
    feature_manifest[field] = value
    manifest.write_text(json.dumps(feature_manifest))
    with pytest.raises(ValueError, match="unsupported feature manifest contract"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="a" * 40)


def test_training_rejects_insufficient_samples(tmp_path):
    dataset, manifest = training_files(tmp_path)
    dataset.write_text(dataset.read_text().splitlines()[0] + "\n")
    metadata = json.loads(manifest.read_text())
    metadata.update({"dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(), "sample_count": 1, "splits": {"train": [0, 1], "validation": [1, 1], "test": [1, 1]}})
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="at least 90"):
        train(dataset,manifest,tmp_path/"model",tmp_path/"report",tracking_uri="sqlite:///:memory:",experiment="test",model_name="test")


def test_training_rejects_missing_classes(tmp_path):
    dataset, manifest = training_files(tmp_path, labels=("LOW",))
    with pytest.raises(ValueError, match="train split lacks class coverage"):
        train(dataset, manifest, tmp_path / "model", tmp_path / "report", tracking_uri="sqlite:///:memory:", experiment="test", model_name="test")


def test_mlflow_failure_is_explicit(tmp_path, monkeypatch):
    dataset, manifest = training_files(tmp_path)
    monkeypatch.setattr("scripts.train_historical_model.mlflow.set_tracking_uri", lambda _: (_ for _ in ()).throw(RuntimeError("MLflow unavailable")))
    with pytest.raises(RuntimeError, match="MLflow unavailable"):
        train(dataset, manifest, tmp_path / "model", tmp_path / "report", tracking_uri="broken", experiment="test", model_name="test")


def test_training_is_deterministic(tmp_path):
    dataset, manifest = training_files(tmp_path)
    reports = []
    for run in (1, 2):
        reports.append(
            train(
                dataset,
                manifest,
                tmp_path / f"model-{run}.joblib",
                tmp_path / f"report-{run}.json",
                tracking_uri=f"sqlite:///{tmp_path / f'mlflow-{run}.db'}",
                experiment="determinism-test",
                model_name=f"determinism-test-{run}",
            )
        )
    assert reports[0]["exported_joblib_sha256"] == reports[1]["exported_joblib_sha256"]
    assert reports[0]["validation"] == reports[1]["validation"]
    assert reports[0]["test"] == reports[1]["test"]


def test_duplicate_feature_decision_id_fails_closed(tmp_path):
    features, manifest, labels = files(tmp_path)
    features.write_text(features.read_text() * 2)
    metadata = json.loads(manifest.read_text())
    metadata["sha256"] = hashlib.sha256(features.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="duplicate feature decision_id"):
        prepare_training_dataset(features, manifest, labels, tmp_path / "out", tmp_path / "meta", training_cutoff=datetime(2026, 1, 3, tzinfo=UTC), git_revision="a" * 40)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("event_time", "2026-01-01T00:00:00Z", "point-in-time ordering"),
        ("ingested_at", "2026-01-01T00:01:00Z", "point-in-time ordering"),
        ("focus_ratio", 0.1, "ratios do not match"),
        ("hours_to_deadline", float("inf"), "finite number"),
    ],
)
def test_feature_row_invariants_fail_closed(tmp_path, field, value, message):
    features, manifest, labels = files(tmp_path)
    feature = json.loads(features.read_text())
    feature[field] = value
    features.write_text(json.dumps(feature) + "\n")
    metadata = json.loads(manifest.read_text())
    metadata["sha256"] = hashlib.sha256(features.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match=message):
        prepare_training_dataset(features, manifest, labels, tmp_path / "out", tmp_path / "meta", training_cutoff=datetime(2026, 1, 3, tzinfo=UTC), git_revision="a" * 40)


def test_decision_after_training_cutoff_fails_closed(tmp_path):
    features, manifest, labels = files(tmp_path)
    with pytest.raises(ValueError, match="feature decision is after training cutoff"):
        prepare_training_dataset(features, manifest, labels, tmp_path / "out", tmp_path / "meta", training_cutoff=datetime(2025, 12, 31, tzinfo=UTC), git_revision="a" * 40)


def test_label_availability_cannot_precede_event(tmp_path):
    features, manifest, labels = files(tmp_path)
    label = json.loads(labels.read_text())
    label["available_at"] = "2025-12-31T23:59:00Z"
    labels.write_text(json.dumps(label) + "\n")
    with pytest.raises(ValueError, match="label availability precedes"):
        prepare_training_dataset(features, manifest, labels, tmp_path / "out", tmp_path / "meta", training_cutoff=datetime(2026, 1, 3, tzinfo=UTC), git_revision="a" * 40)


def test_label_event_cannot_precede_decision(tmp_path):
    features, manifest, labels = files(tmp_path)
    label = json.loads(labels.read_text())
    label["event_time"] = "2025-12-31T23:59:00Z"
    labels.write_text(json.dumps(label) + "\n")
    with pytest.raises(ValueError, match="label event precedes decision"):
        prepare_training_dataset(features, manifest, labels, tmp_path / "out", tmp_path / "meta", training_cutoff=datetime(2026, 1, 3, tzinfo=UTC), git_revision="a" * 40)


@pytest.mark.parametrize(
    "mutation,message",
    [
        ({"splits": {"train": [0, 50], "validation": [51, 72], "test": [72, 90]}}, "split boundaries"),
        ({"git_revision": "not-a-commit"}, "manifest contract"),
        ({"sample_count": 89}, "sample count"),
        ({"dataset_sha256": "bad"}, "checksum is invalid"),
        ({"source_dataset": "s3a://untrusted/data"}, "source lineage"),
        ({"label_availability_cutoff": "2026-01-14T00:00:00+00:00"}, "cutoff is invalid"),
        ({"feature_names": list(reversed(FEATURE_NAMES))}, "manifest contract"),
    ],
)
def test_training_manifest_lineage_fails_closed(tmp_path, mutation, message):
    dataset, manifest = training_files(tmp_path)
    metadata = json.loads(manifest.read_text())
    metadata.update(mutation)
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match=message):
        train(dataset, manifest, tmp_path / "model", tmp_path / "report", tracking_uri="sqlite:///:memory:", experiment="test", model_name="test")


def test_training_dataset_order_and_ratios_fail_closed(tmp_path):
    dataset, manifest = training_files(tmp_path)
    rows = dataset.read_text().splitlines()
    dataset.write_text("\n".join(reversed(rows)) + "\n")
    metadata = json.loads(manifest.read_text())
    metadata["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="chronologically ordered"):
        train(dataset, manifest, tmp_path / "model", tmp_path / "report", tracking_uri="sqlite:///:memory:", experiment="test", model_name="test")

    dataset, manifest = training_files(tmp_path)
    rows = [json.loads(line) for line in dataset.read_text().splitlines()]
    rows[0]["focus_ratio"] = 0.1
    dataset.write_text("".join(json.dumps(row) + "\n" for row in rows))
    metadata = json.loads(manifest.read_text())
    metadata["dataset_sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="ratios are inconsistent"):
        train(dataset, manifest, tmp_path / "model", tmp_path / "report", tracking_uri="sqlite:///:memory:", experiment="test", model_name="test")
