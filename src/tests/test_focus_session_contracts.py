"""Focus-session target and additive v1 contract tests."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cogniflow_contracts import (
    CONTRACT_MODELS,
    BehavioralActivityEvent,
    CvFeatureWindowEvent,
    EffortBand,
    EffortLabelEvent,
    NotificationEvent,
    PredictionResultEvent,
    SessionLifecycleEvent,
    contract_schema_filename,
    effort_band,
    validate_label_history,
    validate_lifecycle,
    validate_unique_events,
)
from scripts.export_focus_session_schemas import export_schemas

START = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
END = START + timedelta(minutes=5)
INGESTED = END + timedelta(seconds=2)
SESSION_ID = "session-001"
WINDOW_ID = UUID("10000000-0000-0000-0000-000000000001")


def envelope(*, event_time: datetime = END, suffix: str = "1") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": uuid4(),
        "session_id": SESSION_ID,
        "subject_id": "subject_001",
        "event_time": event_time,
        "ingested_at": max(INGESTED, event_time),
        "source": "pytest",
        "producer_version": "1.0.0",
        "idempotency_key": f"session-001:{suffix}",
    }


def window(*, event_time: datetime = END, suffix: str = "1") -> dict[str, object]:
    return {
        **envelope(event_time=event_time, suffix=suffix),
        "window_id": WINDOW_ID,
        "window_start": START,
        "window_end": END,
        "feature_cutoff": END,
    }


def lifecycle(event_type: str, sequence: int, at: datetime) -> SessionLifecycleEvent:
    return SessionLifecycleEvent.model_validate(
        {
            **envelope(event_time=at, suffix=str(sequence)),
            "ingested_at": at,
            "event_type": event_type,
            "sequence": sequence,
            "session_kind": "programming",
            "privacy_mode": "behavioral",
            "planned_duration_seconds": 1500,
        }
    )


def label(**updates: object) -> EffortLabelEvent:
    payload = {
        **window(event_time=INGESTED, suffix=str(uuid4())),
        "event_type": "effort.reported",
        "label_id": uuid4(),
        "effort_rating": 5,
        "reported_at": INGESTED,
        "confidence": 4,
    }
    payload.update(updates)
    return EffortLabelEvent.model_validate(payload)


def prediction(**updates: object) -> PredictionResultEvent:
    payload = {
        **window(event_time=INGESTED, suffix="prediction-1"),
        "event_type": "prediction.completed",
        "prediction_id": uuid4(),
        "target_name": "self_reported_effort",
        "predicted_effort_rating": 5.49,
        "effort_band": "MEDIUM",
        "class_probabilities": None,
        "model_name": "focus-session-model",
        "model_version": "1",
        "run_id": "0123456789abcdef0123456789abcdef",
        "model_sha256": "1" * 64,
        "dataset_sha256": "2" * 64,
        "behavioral_contract_version": "1.0",
        "cv_contract_version": None,
        "cv_available": False,
        "feature_as_of": END,
        "label_window_ids_used": (),
        "inference_latency_ms": 12.5,
        "inference_source": "local_model",
    }
    payload.update(updates)
    return PredictionResultEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1, EffortBand.LOW),
        (2.499, EffortBand.LOW),
        (2.5, EffortBand.MEDIUM),
        (5.499, EffortBand.MEDIUM),
        (5.5, EffortBand.HIGH),
        (7, EffortBand.HIGH),
    ],
)
def test_continuous_effort_band_projection(score, expected):
    assert effort_band(score) is expected


@pytest.mark.parametrize("score", [0.99, 7.01, math.inf, math.nan])
def test_effort_band_rejects_out_of_range_or_nonfinite_scores(score):
    with pytest.raises(ValueError, match="effort score"):
        effort_band(score)


def test_valid_lifecycle_is_ordered_and_terminal():
    events = [
        lifecycle("session.started", 1, START),
        lifecycle("session.paused", 2, START + timedelta(minutes=1)),
        lifecycle("session.resumed", 3, START + timedelta(minutes=2)),
        lifecycle("session.completed", 4, END),
    ]
    validate_lifecycle(events)


@pytest.mark.parametrize(
    "events, message",
    [
        ([lifecycle("session.paused", 1, START)], "begin"),
        (
            [lifecycle("session.started", 1, START), lifecycle("session.started", 2, END)],
            "illegal",
        ),
        (
            [lifecycle("session.started", 1, START), lifecycle("session.completed", 3, END)],
            "gaps",
        ),
        (
            [
                lifecycle("session.started", 1, START),
                lifecycle("session.paused", 1, END).model_copy(
                    update={"idempotency_key": "session-001:second"}
                ),
            ],
            "increase",
        ),
    ],
)
def test_lifecycle_rejects_invalid_start_transition_or_sequence(events, message):
    with pytest.raises(ValueError, match=message):
        validate_lifecycle(events)


def test_lifecycle_rejects_duplicate_identifiers():
    first = lifecycle("session.started", 1, START)
    duplicate = lifecycle("session.completed", 2, END).model_copy(
        update={"event_id": first.event_id}
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_lifecycle([first, duplicate])


def test_generic_collection_rejects_duplicate_event_identifiers():
    event = lifecycle("session.started", 1, START)
    with pytest.raises(ValueError, match="duplicate"):
        validate_unique_events([event, event])


def test_behavioral_window_is_strict_and_completed():
    event = BehavioralActivityEvent.model_validate(
        {
            **window(),
            "event_type": "behavioral.window",
            "active_seconds": 240,
            "idle_seconds": 60,
            "keyboard_event_count": 120,
            "pointer_event_count": 30,
            "application_switch_count": 2,
            "build_count": 1,
            "test_count": 3,
        }
    )
    assert event.feature_cutoff == event.window_end
    assert event.active_seconds + event.idle_seconds == 300


def test_behavioral_contract_rejects_missing_required_field():
    payload = {
        **window(),
        "event_type": "behavioral.window",
        "active_seconds": 240,
        "idle_seconds": 60,
        "keyboard_event_count": 120,
        "pointer_event_count": 30,
    }
    with pytest.raises(ValidationError, match="application_switch_count"):
        BehavioralActivityEvent.model_validate(payload)


@pytest.mark.parametrize(
    "updates",
    [
        {"schema_version": "2.0"},
        {"session_id": "not valid"},
        {"window_end": END + timedelta(seconds=1)},
        {"feature_cutoff": END - timedelta(seconds=1)},
        {"event_time": END + timedelta(seconds=1)},
        {"active_seconds": math.inf},
        {"active_seconds": 250, "idle_seconds": 100},
        {"keystroke_contents": "secret"},
        {"source_code": "print('secret')"},
        {"window_title": "private.py"},
        {"url": "https://private.example"},
        {"filename": "private.py"},
    ],
)
def test_behavioral_contract_rejects_versions_bounds_and_private_fields(updates):
    payload = {
        **window(),
        "event_type": "behavioral.window",
        "active_seconds": 240,
        "idle_seconds": 60,
        "keyboard_event_count": 120,
        "pointer_event_count": 30,
        "application_switch_count": 2,
    }
    payload.update(updates)
    with pytest.raises(ValidationError):
        BehavioralActivityEvent.model_validate(payload)


def test_timestamps_must_be_utc_and_not_future_relative_to_ingestion():
    payload = {**envelope(event_time=END), "event_type": "session.started", "sequence": 1,
               "session_kind": "study", "privacy_mode": "behavioral"}
    with pytest.raises(ValidationError, match="UTC"):
        SessionLifecycleEvent.model_validate(
            {**payload, "event_time": "2026-10-28T07:05:00-05:00"}
        )
    with pytest.raises(ValidationError, match="after ingested"):
        SessionLifecycleEvent.model_validate(
            {**payload, "event_time": END + timedelta(seconds=3), "ingested_at": END}
        )


def test_camera_unavailable_has_explicit_null_features():
    event = CvFeatureWindowEvent.model_validate(
        {
            **window(),
            "event_type": "cv.window",
            "camera_available": False,
            "frames_sampled": 0,
            "frames_processed": 0,
            "frames_dropped": 0,
            "agent_version": "1.0.0",
        }
    )
    assert event.face_presence_ratio is None
    assert event.asset_sha256 is None


def test_available_camera_requires_complete_finite_aggregates_and_asset():
    payload = {
        **window(),
        "event_type": "cv.window",
        "camera_available": True,
        "face_presence_ratio": 0.9,
        "gaze_away_ratio": 0.1,
        "blink_rate_per_minute": 12,
        "head_pose_variance": 0.2,
        "frames_sampled": 100,
        "frames_processed": 95,
        "frames_dropped": 5,
        "agent_version": "1.0.0",
        "asset_name": "face-landmarker-v1",
        "asset_sha256": "a" * 64,
        "cpu_seconds": 20,
        "latency_p50_ms": 20,
        "latency_p95_ms": 50,
    }
    assert CvFeatureWindowEvent.model_validate(payload).frames_processed == 95
    for updates in (
        {"face_presence_ratio": None},
        {"head_pose_variance": math.nan},
        {"frames_dropped": 4},
        {"latency_p50_ms": 51},
        {"facial_landmarks": [[1, 2]]},
        {"face_embedding": [0.1]},
        {"raw_image": "bytes"},
    ):
        with pytest.raises(ValidationError):
            CvFeatureWindowEvent.model_validate({**payload, **updates})


def test_label_preserves_rating_and_derives_band():
    event = label(effort_rating=6)
    assert event.effort_rating == 6
    assert event.compatibility_band is EffortBand.HIGH


@pytest.mark.parametrize("rating", [0, 8, 4.5])
def test_label_rejects_invalid_ratings(rating):
    with pytest.raises(ValidationError):
        label(effort_rating=rating)


def test_label_rejects_before_window_but_accepts_delayed_reports():
    with pytest.raises(ValidationError, match="before"):
        label(event_time=START, reported_at=START, ingested_at=START)
    delayed = END + timedelta(days=2)
    assert label(event_time=delayed, reported_at=delayed, ingested_at=delayed).reported_at == delayed


def test_append_only_label_corrections_accept_out_of_order_input():
    original = label(effort_rating=3)
    corrected_at = original.reported_at + timedelta(minutes=1)
    correction = label(
        event_time=corrected_at,
        ingested_at=corrected_at,
        reported_at=corrected_at,
        effort_rating=4,
        supersedes_label_id=original.label_id,
    )
    validate_label_history([correction, original])
    assert original.effort_rating == 3
    assert correction.effort_rating == 4


def test_label_history_rejects_duplicate_or_invalid_correction():
    original = label()
    with pytest.raises(ValueError, match="duplicate"):
        validate_label_history([original, original])
    orphan = label(supersedes_label_id=uuid4())
    with pytest.raises(ValueError, match="earlier"):
        validate_label_history([orphan])

    corrected_at = original.reported_at + timedelta(minutes=1)
    changed_window = label(
        window_start=START - timedelta(minutes=5),
        window_end=START,
        feature_cutoff=START,
        event_time=corrected_at,
        ingested_at=corrected_at,
        reported_at=corrected_at,
        supersedes_label_id=original.label_id,
    )
    with pytest.raises(ValueError, match="window boundaries"):
        validate_label_history([original, changed_window])


def test_prediction_has_strict_provenance_and_no_invented_probabilities():
    event = prediction()
    assert event.target_name == "self_reported_effort"
    assert event.class_probabilities is None
    assert event.effort_band is EffortBand.MEDIUM


@pytest.mark.parametrize(
    "updates, message",
    [
        ({"effort_band": "HIGH"}, "effort_band"),
        ({"feature_as_of": END - timedelta(seconds=1)}, "feature_as_of"),
        ({"event_time": END - timedelta(seconds=1)}, "feature cutoff"),
        ({"label_window_ids_used": (WINDOW_ID,)}, "target window label"),
        ({"label_window_ids_used": (uuid4(),) * 2}, "duplicates"),
        ({"model_sha256": "mutable-tag"}, "model_sha256"),
        ({"cv_available": True}, "CV availability"),
        ({"class_probabilities": (0.2, 0.2, 0.2)}, "sum"),
        ({"class_probabilities": (0.2, math.nan, 0.8)}, "finite"),
    ],
)
def test_prediction_rejects_leakage_timing_and_invalid_provenance(updates, message):
    with pytest.raises(ValidationError, match=message):
        prediction(**updates)


@pytest.mark.parametrize(
    "event_type, attempts, failure, suppression",
    [
        ("notification.requested", 0, None, None),
        ("notification.delivered", 1, None, None),
        ("notification.failed", 3, "retries_exhausted", None),
        ("notification.suppressed", 0, None, "duplicate"),
    ],
)
def test_valid_notification_delivery_states(event_type, attempts, failure, suppression):
    event = NotificationEvent.model_validate(
        {
            **envelope(suffix=event_type),
            "event_type": event_type,
            "notification_id": uuid4(),
            "prediction_id": uuid4(),
            "rule_id": "high-effort",
            "rule_version": "1",
            "deduplication_key": "rule:prediction:discord",
            "attempt_count": attempts,
            "failure_code": failure,
            "suppression_reason": suppression,
        }
    )
    assert event.channel == "discord_webhook"


def test_notification_rejects_invalid_state_and_credentials():
    payload = {
        **envelope(),
        "event_type": "notification.delivered",
        "notification_id": uuid4(),
        "prediction_id": uuid4(),
        "rule_id": "high-effort",
        "rule_version": "1",
        "deduplication_key": "rule:prediction:discord",
        "attempt_count": 0,
    }
    with pytest.raises(ValidationError, match="delivery state"):
        NotificationEvent.model_validate(payload)
    for secret in ("webhook_url", "discord_token", "authorization"):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            NotificationEvent.model_validate({**payload, "attempt_count": 1, secret: "secret"})


def test_schema_export_is_complete_and_deterministic(tmp_path):
    first = export_schemas(tmp_path)
    before = {path.name: path.read_bytes() for path in first}
    second = export_schemas(tmp_path)
    assert len(first) == len(second) == 6
    assert before == {path.name: path.read_bytes() for path in second}
    for topic, model in CONTRACT_MODELS.items():
        schema = json.loads((tmp_path / contract_schema_filename(topic)).read_text())
        assert schema == model.model_json_schema()
        assert schema["additionalProperties"] is False


def test_committed_schemas_match_models():
    root = Path(__file__).parents[2] / "docs/focus-session/schemas"
    for topic, model in CONTRACT_MODELS.items():
        assert json.loads((root / contract_schema_filename(topic)).read_text()) == model.model_json_schema()
