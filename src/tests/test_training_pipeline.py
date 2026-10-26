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
        rows.append(
            {
                "decision_id": f"d{index:03d}",
                "decision_time": (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index)).isoformat(),
                **{name: index % 11 for name in FEATURE_NAMES},
                "label": label,
            }
        )
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("".join(json.dumps(row) + "\n" for row in rows))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "feature_names": list(FEATURE_NAMES),
                "git_revision": "test-revision",
                "training_cutoff": "2026-01-15T00:00:00+00:00",
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
    return prepare_training_dataset(*paths, tmp_path/"dataset.jsonl", tmp_path/"manifest.json", training_cutoff=datetime(2026,1,3,tzinfo=UTC), git_revision="abc123")


def test_join_preserves_temporal_and_lineage_contract(tmp_path):
    result = prepare(tmp_path)
    assert result["sample_count"] == 1
    assert result["source_delta_versions"] == []
    assert result["git_revision"] == "abc123"


def test_late_label_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="unavailable by cutoff"):
        prepare(tmp_path, label_delay=4)


def test_duplicate_and_missing_labels_fail_closed(tmp_path):
    features, manifest, labels = files(tmp_path)
    labels.write_text(labels.read_text()*2)
    with pytest.raises(ValueError, match="duplicate label"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="x")
    labels.write_text("")
    with pytest.raises(ValueError, match="missing label"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="x")


def test_manifest_tampering_and_future_feature_fail_closed(tmp_path):
    features, manifest, labels = files(tmp_path)
    features.write_text(features.read_text()+" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="x")

    feature = json.loads(features.read_text())
    feature["available_at"] = "2026-01-01T01:00:00Z"
    features.write_text(json.dumps(feature) + "\n")
    feature_manifest = json.loads(manifest.read_text())
    feature_manifest["sha256"] = hashlib.sha256(features.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(feature_manifest))
    with pytest.raises(ValueError, match="future feature availability"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="x")


@pytest.mark.parametrize("field,value", [("feature_schema_version", "2.0"), ("feature_names", list(reversed(FEATURE_NAMES)))])
def test_feature_manifest_contract_fails_closed(tmp_path, field, value):
    features, manifest, labels = files(tmp_path)
    feature_manifest = json.loads(manifest.read_text())
    feature_manifest[field] = value
    manifest.write_text(json.dumps(feature_manifest))
    with pytest.raises(ValueError, match="unsupported feature manifest contract"):
        prepare_training_dataset(features,manifest,labels,tmp_path/"out",tmp_path/"meta",training_cutoff=datetime(2026,1,3,tzinfo=UTC),git_revision="x")


def test_training_rejects_insufficient_samples(tmp_path):
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(json.dumps({"decision_time":"2026-01-01T00:00:00Z","decision_id":"d1",**dict.fromkeys(FEATURE_NAMES,0),"label":"LOW"})+"\n")
    import hashlib
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"dataset_sha256":hashlib.sha256(dataset.read_bytes()).hexdigest(),"feature_names":list(FEATURE_NAMES),"splits":{"train":[0,1],"validation":[1,1],"test":[1,1]}}))
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
    assert reports[0]["model_sha256"] == reports[1]["model_sha256"]
    assert reports[0]["validation"] == reports[1]["validation"]
    assert reports[0]["test"] == reports[1]["test"]
