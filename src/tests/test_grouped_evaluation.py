"""Independent feature groups, deterministic membership and predeclared selection."""

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from cogniflow_data.training import (
    GROUP_SPLIT, feature_group, grouped_splits, prepare_training_dataset,
    select_candidate, split_identity, split_training_frame, validate_training_manifest,
)
from scripts.generate_training_fixture import generate_fixture


def prepared(tmp_path):
    generate_fixture(tmp_path / "features", tmp_path / "labels", tmp_path / "features.json", 210)
    dataset = tmp_path / "dataset.jsonl"
    manifest = prepare_training_dataset(
        tmp_path / "features", tmp_path / "features.json", tmp_path / "labels",
        dataset, tmp_path / "manifest.json", training_cutoff=datetime(2026, 1, 15, tzinfo=UTC),
        git_revision="a" * 40, split_protocol=GROUP_SPLIT,
    )
    return dataset, manifest


def test_group_membership_is_disjoint_complete_class_preserving_and_deterministic(tmp_path):
    dataset, manifest = prepared(tmp_path)
    frame = pd.read_json(dataset, lines=True)
    validate_training_manifest(manifest, dataset)
    parts = split_training_frame(frame, manifest)
    groups = [{feature_group(row) for row in part.to_dict("records")} for part in parts]
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    assert [len(group) for group in groups] == [36, 12, 12]
    assert sum(len(part) for part in parts) == 210
    assert all(set(part["label"]) == {"LOW", "MEDIUM", "HIGH"} for part in parts)
    assert sorted(index for rows in manifest["splits"].values() for index in rows) == list(range(210))
    assert grouped_splits(frame.to_dict("records")) == manifest["splits"]
    reversed_rows = frame.iloc[::-1].to_dict("records")
    reversed_splits = grouped_splits(reversed_rows)
    for expected, indices in zip(groups, reversed_splits.values()):
        assert expected == {feature_group(reversed_rows[index]) for index in indices}


def test_rehashed_overlapping_membership_is_rejected(tmp_path):
    dataset, manifest = prepared(tmp_path)
    manifest["splits"]["test"][0] = manifest["splits"]["train"][0]
    manifest["split_sha256"] = split_identity(manifest)
    with pytest.raises(ValueError, match="group split membership"):
        split_training_frame(pd.read_json(dataset, lines=True), manifest)


def test_split_identity_tampering_is_rejected(tmp_path):
    dataset, manifest = prepared(tmp_path)
    manifest["split_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="split identity"):
        validate_training_manifest(manifest, dataset)


def test_conflicting_labels_and_insufficient_groups_fail_closed(tmp_path):
    dataset, _ = prepared(tmp_path)
    rows = [json.loads(line) for line in dataset.read_text().splitlines()]
    rows.append({**rows[0], "label": "HIGH"})
    with pytest.raises(ValueError, match="conflicting labels"):
        grouped_splits(rows)
    with pytest.raises(ValueError, match="three groups per class"):
        grouped_splits(rows[:3])


def test_group_key_ignores_identity_and_normalizes_numeric_types():
    row = {"focus_minutes": 0, "distraction_minutes": 1, "tasks_due": 2, "hours_to_deadline": 3}
    assert feature_group(row) == feature_group({**row, "focus_minutes": -0.0,
                                               "tasks_due": 2.0, "decision_id": "other"})


def test_selection_prefers_accuracy_then_simpler_exact_tie_and_rejects_nan():
    metrics = {name: {"accuracy": .9, "macro_f1": .8} for name in
               ("random_forest", "logistic_regression", "dummy_majority")}
    assert select_candidate(metrics) == "dummy_majority"
    metrics["dummy_majority"]["macro_f1"] = .2
    assert select_candidate(metrics) == "logistic_regression"
    metrics["random_forest"]["accuracy"] = .95
    assert select_candidate(metrics) == "random_forest"
    metrics["random_forest"]["macro_f1"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        select_candidate(metrics)
