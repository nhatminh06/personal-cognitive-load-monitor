from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from cogniflow_data.historical import (
    FEATURE_SCHEMA_VERSION,
    FeatureDecision,
    SilverFeatureEvent,
    SourceSnapshot,
    SyntheticLabel,
    available_labels,
    select_historical_features,
    write_dataset,
)
from cogniflow_data.online import OnlineFeatureRecord
from preprocessing_api.features import FEATURE_NAMES

FIXTURE = json.loads((Path(__file__).parents[2] / "tests/fixtures/historical_features.json").read_text())


def inputs():
    return (
        [SilverFeatureEvent.model_validate(item) for item in FIXTURE["events"]],
        [FeatureDecision.model_validate(item) for item in FIXTURE["decisions"]],
        SourceSnapshot.model_validate(FIXTURE["snapshot"]),
    )


def test_point_in_time_selection_blocks_future_and_late_data_and_breaks_ties():
    events, decisions, snapshot = inputs()
    rows = select_historical_features([events[3], events[2], events[0], events[1], events[4]], decisions, snapshot)

    assert [row.decision_id for row in rows] == ["decision-1", "decision-2"]
    assert str(rows[0].event_id).endswith("0002")
    assert rows[0].ordered_features() == pytest.approx([90, 30, 2, 20, 0.75, 0.25])
    assert rows[0].feature_names == FEATURE_NAMES
    assert rows[0].feature_schema_version == FEATURE_SCHEMA_VERSION
    assert rows[1].event_time == datetime(2026, 1, 1, 8, tzinfo=UTC)


def test_duplicate_replay_is_deterministic_and_conflicts_fail_closed():
    events, decisions, snapshot = inputs()
    first = select_historical_features(events + [events[0]], decisions, snapshot)
    second = select_historical_features(list(reversed(events + [events[0]])), decisions, snapshot)
    assert first == second

    conflicting = events[0].model_copy(update={"tasks_due": 99})
    with pytest.raises(ValueError, match="conflicting duplicate"):
        select_historical_features(events + [conflicting], decisions, snapshot)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "2.0"},
        {"focus_ratio": float("nan")},
        {"hours_to_deadline": float("inf")},
        {"event_time": "2026-01-01T10:00:00"},
    ],
)
def test_invalid_contract_values_are_rejected(change):
    value = {**FIXTURE["events"][0], **change}
    with pytest.raises(ValidationError):
        SilverFeatureEvent.model_validate(value)


def test_labels_are_separate_and_only_available_by_cutoff():
    labels = [
        SyntheticLabel(decision_id="decision-1", label="HIGH", event_time="2026-01-02T00:00:00Z", available_at="2026-01-03T00:00:00Z"),
        SyntheticLabel(decision_id="decision-2", label="LOW", event_time="2026-01-02T00:00:00Z", available_at="2026-01-04T00:00:00Z"),
    ]
    assert list(available_labels(labels, datetime(2026, 1, 3, tzinfo=UTC))) == ["decision-1"]


def test_historical_and_online_vectors_match_but_have_distinct_roles():
    events, decisions, snapshot = inputs()
    row = select_historical_features(events, decisions, snapshot)[0]
    online = OnlineFeatureRecord(
        session_id=row.session_id, feature_timestamp=row.event_time, schema_version="1.0",
        provenance="flink:kafka:cogniflow.session-events.v1", **{name: getattr(row, name) for name in FEATURE_NAMES},
    )
    assert [float(getattr(online, name)) for name in FEATURE_NAMES] == pytest.approx(row.ordered_features(), abs=1e-12)
    assert row.source_delta_version == 1
    assert online.provenance.startswith("flink:")


def test_artifact_manifest_is_reproducible(tmp_path):
    events, decisions, snapshot = inputs()
    rows = select_historical_features(events, decisions, snapshot)
    first = write_dataset(rows, tmp_path / "one.jsonl", tmp_path / "one.json", code_revision="test")
    second = write_dataset(rows, tmp_path / "two.jsonl", tmp_path / "two.json", code_revision="test")
    assert first == second
    assert first["row_count"] == 2
    assert (tmp_path / "one.jsonl").read_bytes() == (tmp_path / "two.jsonl").read_bytes()
