"""Strict, additive focus-session event contracts."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION: Literal["1.0"] = "1.0"
WINDOW_DURATION = timedelta(minutes=5)
TARGET_NAME: Literal["self_reported_effort"] = "self_reported_effort"
SESSION_ID_PATTERN = r"^[A-Za-z0-9._:-]+$"
TOKEN_PATTERN = r"^[A-Za-z0-9._:-]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

SESSION_LIFECYCLE_TOPIC = "cogniflow.session-lifecycle.v1"
BEHAVIORAL_ACTIVITY_TOPIC = "cogniflow.behavioral-activity.v1"
CV_FEATURES_TOPIC = "cogniflow.cv-features.v1"
EFFORT_LABELS_TOPIC = "cogniflow.effort-labels.v1"
PREDICTIONS_TOPIC = "cogniflow.predictions.v1"
NOTIFICATIONS_TOPIC = "cogniflow.notifications.v1"


class EffortBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def effort_band(score: int | float) -> EffortBand:
    """Project a finite 1–7 score using half-step ordinal boundaries."""

    value = float(score)
    if not math.isfinite(value) or not 1 <= value <= 7:
        raise ValueError("effort score must be finite and between 1 and 7")
    if value < 2.5:
        return EffortBand.LOW
    if value < 5.5:
        return EffortBand.MEDIUM
    return EffortBand.HIGH


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return value.astimezone(UTC)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EventEnvelope(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    event_id: UUID = Field(default_factory=uuid4)
    session_id: str = Field(min_length=1, max_length=128, pattern=SESSION_ID_PATTERN)
    subject_id: str | None = Field(
        default=None, min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    event_time: datetime
    ingested_at: datetime
    source: str = Field(min_length=1, max_length=64, pattern=TOKEN_PATTERN)
    producer_version: str = Field(min_length=1, max_length=32, pattern=TOKEN_PATTERN)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=TOKEN_PATTERN)

    @field_validator("event_time", "ingested_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def event_not_after_ingestion(self) -> Self:
        if self.event_time > self.ingested_at:
            raise ValueError("event_time cannot be after ingested_at")
        return self


class SessionLifecycleEvent(EventEnvelope):
    event_type: Literal[
        "session.started",
        "session.paused",
        "session.resumed",
        "session.completed",
        "session.cancelled",
    ]
    sequence: int = Field(ge=1)
    session_kind: Literal["programming", "study"]
    privacy_mode: Literal["behavioral", "behavioral_cv"]
    planned_duration_seconds: int | None = Field(default=None, ge=300, le=28_800)


_NEXT_LIFECYCLE_EVENTS = {
    "session.started": {"session.paused", "session.completed", "session.cancelled"},
    "session.paused": {"session.resumed", "session.completed", "session.cancelled"},
    "session.resumed": {"session.paused", "session.completed", "session.cancelled"},
    "session.completed": set(),
    "session.cancelled": set(),
}


def validate_unique_events(events: Sequence[EventEnvelope]) -> None:
    """Reject duplicate wire identities in an event collection."""

    event_ids: set[UUID] = set()
    idempotency_keys: set[str] = set()
    for event in events:
        if event.event_id in event_ids or event.idempotency_key in idempotency_keys:
            raise ValueError("event collection contains a duplicate identifier")
        event_ids.add(event.event_id)
        idempotency_keys.add(event.idempotency_key)


def validate_lifecycle(events: list[SessionLifecycleEvent]) -> None:
    """Validate one session's ordered, append-only lifecycle stream."""

    if not events:
        raise ValueError("lifecycle stream cannot be empty")
    if events[0].event_type != "session.started" or events[0].sequence != 1:
        raise ValueError("lifecycle must begin with sequence 1 session.started")
    validate_unique_events(events)
    first = events[0]
    previous = first
    for event in events:
        if event.session_id != first.session_id:
            raise ValueError("lifecycle stream contains multiple sessions")
        if event.session_kind != first.session_kind or event.privacy_mode != first.privacy_mode:
            raise ValueError("session lifecycle metadata cannot change")
        if event is first:
            continue
        if event.sequence <= previous.sequence:
            raise ValueError("lifecycle sequence must increase monotonically")
        if event.sequence != previous.sequence + 1:
            raise ValueError("lifecycle sequence cannot contain gaps")
        if event.event_time < previous.event_time:
            raise ValueError("lifecycle event_time cannot move backwards")
        if event.event_type not in _NEXT_LIFECYCLE_EVENTS[previous.event_type]:
            raise ValueError("illegal lifecycle transition")
        previous = event


class FiveMinuteWindow(EventEnvelope):
    window_id: UUID
    window_start: datetime
    window_end: datetime
    feature_cutoff: datetime

    @field_validator("window_start", "window_end", "feature_cutoff")
    @classmethod
    def utc_window_timestamp(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def completed_window(self) -> Self:
        if self.window_end - self.window_start != WINDOW_DURATION:
            raise ValueError("window must be exactly five minutes")
        if self.feature_cutoff != self.window_end:
            raise ValueError("feature_cutoff must equal window_end")
        return self


class BehavioralActivityEvent(FiveMinuteWindow):
    event_type: Literal["behavioral.window"] = "behavioral.window"
    active_seconds: float = Field(ge=0, le=300, allow_inf_nan=False)
    idle_seconds: float = Field(ge=0, le=300, allow_inf_nan=False)
    keyboard_event_count: int = Field(ge=0, le=1_000_000)
    pointer_event_count: int = Field(ge=0, le=1_000_000)
    application_switch_count: int = Field(ge=0, le=100_000)
    build_count: int | None = Field(default=None, ge=0, le=100_000)
    test_count: int | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def bounded_observation(self) -> Self:
        if self.event_time != self.window_end:
            raise ValueError("behavioral event_time must equal window_end")
        if self.active_seconds + self.idle_seconds > 300:
            raise ValueError("active and idle seconds exceed the window")
        return self


class CvFeatureWindowEvent(FiveMinuteWindow):
    event_type: Literal["cv.window"] = "cv.window"
    camera_available: bool
    face_presence_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    gaze_away_ratio: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    blink_rate_per_minute: float | None = Field(default=None, ge=0, le=300, allow_inf_nan=False)
    head_pose_variance: float | None = Field(default=None, ge=0, le=10_000, allow_inf_nan=False)
    frames_sampled: int = Field(ge=0, le=100_000)
    frames_processed: int = Field(ge=0, le=100_000)
    frames_dropped: int = Field(ge=0, le=100_000)
    agent_version: str = Field(min_length=1, max_length=32, pattern=TOKEN_PATTERN)
    asset_name: str | None = Field(default=None, min_length=1, max_length=128, pattern=TOKEN_PATTERN)
    asset_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    cpu_seconds: float | None = Field(default=None, ge=0, le=300, allow_inf_nan=False)
    latency_p50_ms: float | None = Field(default=None, ge=0, le=60_000, allow_inf_nan=False)
    latency_p95_ms: float | None = Field(default=None, ge=0, le=60_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def camera_fields_are_consistent(self) -> Self:
        if self.event_time != self.window_end:
            raise ValueError("CV event_time must equal window_end")
        features = (
            self.face_presence_ratio,
            self.gaze_away_ratio,
            self.blink_rate_per_minute,
            self.head_pose_variance,
            self.cpu_seconds,
            self.latency_p50_ms,
            self.latency_p95_ms,
        )
        if not self.camera_available:
            if any(value is not None for value in features) or self.asset_name or self.asset_sha256:
                raise ValueError("unavailable camera must not contain CV features or assets")
            if self.frames_sampled or self.frames_processed or self.frames_dropped:
                raise ValueError("unavailable camera must have zero frame counts")
            return self
        if any(value is None for value in features) or not self.asset_name or not self.asset_sha256:
            raise ValueError("available camera requires complete aggregate features and asset identity")
        if self.frames_sampled <= 0 or self.frames_processed + self.frames_dropped != self.frames_sampled:
            raise ValueError("CV frame counts are inconsistent")
        if self.latency_p50_ms is not None and self.latency_p95_ms is not None:
            if self.latency_p50_ms > self.latency_p95_ms:
                raise ValueError("CV latency p50 cannot exceed p95")
        return self


class EffortLabelEvent(FiveMinuteWindow):
    event_type: Literal["effort.reported"] = "effort.reported"
    label_id: UUID = Field(default_factory=uuid4)
    effort_rating: int = Field(ge=1, le=7)
    reported_at: datetime
    label_source: Literal["user_self_report"] = "user_self_report"
    confidence: int | None = Field(default=None, ge=1, le=5)
    supersedes_label_id: UUID | None = None

    @field_validator("reported_at")
    @classmethod
    def utc_reported_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def label_timing_and_identity(self) -> Self:
        if self.reported_at < self.window_end:
            raise ValueError("label cannot be reported before its window completes")
        if self.event_time != self.reported_at:
            raise ValueError("label event_time must equal reported_at")
        if self.supersedes_label_id == self.label_id:
            raise ValueError("label cannot supersede itself")
        return self

    @property
    def compatibility_band(self) -> EffortBand:
        return effort_band(self.effort_rating)


def validate_label_history(labels: list[EffortLabelEvent]) -> None:
    """Validate append-only corrections while accepting delayed/out-of-order input."""

    if not labels:
        raise ValueError("label history cannot be empty")
    event_ids: set[UUID] = set()
    label_ids: set[UUID] = set()
    idempotency_keys: set[str] = set()
    ordered = sorted(labels, key=lambda label: (label.reported_at, str(label.label_id)))
    first = ordered[0]
    latest_by_window: dict[UUID, EffortLabelEvent] = {}
    for label in ordered:
        if label.session_id != first.session_id:
            raise ValueError("label history contains multiple sessions")
        if (
            label.event_id in event_ids
            or label.label_id in label_ids
            or label.idempotency_key in idempotency_keys
        ):
            raise ValueError("label history contains a duplicate identifier")
        event_ids.add(label.event_id)
        label_ids.add(label.label_id)
        idempotency_keys.add(label.idempotency_key)
        previous = latest_by_window.get(label.window_id)
        if previous is None:
            if label.supersedes_label_id is not None:
                raise ValueError("label correction does not reference an earlier label")
        else:
            if (label.window_start, label.window_end) != (previous.window_start, previous.window_end):
                raise ValueError("label correction cannot change window boundaries")
            if label.supersedes_label_id != previous.label_id:
                raise ValueError("label correction must supersede the latest label for its window")
        latest_by_window[label.window_id] = label


class PredictionResultEvent(FiveMinuteWindow):
    event_type: Literal["prediction.completed"] = "prediction.completed"
    prediction_id: UUID = Field(default_factory=uuid4)
    target_name: Literal["self_reported_effort"] = TARGET_NAME
    predicted_effort_rating: float = Field(ge=1, le=7, allow_inf_nan=False)
    effort_band: EffortBand
    class_probabilities: tuple[float, float, float] | None = None
    model_name: str = Field(min_length=1, max_length=128, pattern=TOKEN_PATTERN)
    model_version: str = Field(min_length=1, max_length=64, pattern=TOKEN_PATTERN)
    run_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    model_sha256: str = Field(pattern=SHA256_PATTERN)
    dataset_sha256: str = Field(pattern=SHA256_PATTERN)
    behavioral_contract_version: Literal["1.0"] = SCHEMA_VERSION
    cv_contract_version: Literal["1.0"] | None = None
    cv_available: bool
    feature_as_of: datetime
    label_window_ids_used: tuple[UUID, ...] = ()
    inference_latency_ms: float = Field(ge=0, le=300_000, allow_inf_nan=False)
    inference_source: Literal["local_model", "kserve"]

    @field_validator("feature_as_of")
    @classmethod
    def utc_feature_as_of(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def provenance_and_temporal_integrity(self) -> Self:
        if self.feature_as_of != self.feature_cutoff:
            raise ValueError("feature_as_of must equal the feature cutoff")
        if self.event_time < self.feature_as_of:
            raise ValueError("prediction cannot precede its feature cutoff")
        if self.effort_band != effort_band(self.predicted_effort_rating):
            raise ValueError("effort_band does not match predicted_effort_rating")
        if len(set(self.label_window_ids_used)) != len(self.label_window_ids_used):
            raise ValueError("prediction label lineage contains duplicates")
        if self.window_id in self.label_window_ids_used:
            raise ValueError("prediction cannot consume the target window label")
        if self.cv_available != (self.cv_contract_version is not None):
            raise ValueError("CV availability and contract version are inconsistent")
        if self.class_probabilities is not None:
            if any(not math.isfinite(value) or not 0 <= value <= 1 for value in self.class_probabilities):
                raise ValueError("class probabilities must be finite values between 0 and 1")
            if not math.isclose(sum(self.class_probabilities), 1.0, abs_tol=1e-9):
                raise ValueError("class probabilities must sum to 1")
        return self


class NotificationEvent(EventEnvelope):
    event_type: Literal[
        "notification.requested",
        "notification.delivered",
        "notification.failed",
        "notification.suppressed",
    ]
    notification_id: UUID
    prediction_id: UUID
    rule_id: str = Field(min_length=1, max_length=64, pattern=TOKEN_PATTERN)
    rule_version: str = Field(min_length=1, max_length=32, pattern=TOKEN_PATTERN)
    channel: Literal["discord_webhook"] = "discord_webhook"
    deduplication_key: str = Field(min_length=1, max_length=256, pattern=TOKEN_PATTERN)
    attempt_count: int = Field(ge=0, le=3)
    failure_code: Literal[
        "network", "timeout", "rate_limited", "server_error", "client_error", "retries_exhausted"
    ] | None = None
    suppression_reason: Literal["duplicate", "disabled", "cooldown", "rule_not_met"] | None = None

    @model_validator(mode="after")
    def valid_delivery_state(self) -> Self:
        if self.event_type == "notification.requested":
            valid = self.attempt_count == 0 and self.failure_code is None and self.suppression_reason is None
        elif self.event_type == "notification.delivered":
            valid = 1 <= self.attempt_count <= 3 and self.failure_code is None and self.suppression_reason is None
        elif self.event_type == "notification.failed":
            valid = 1 <= self.attempt_count <= 3 and self.failure_code is not None and self.suppression_reason is None
        else:
            valid = self.attempt_count == 0 and self.failure_code is None and self.suppression_reason is not None
        if not valid:
            raise ValueError("notification delivery state is inconsistent")
        return self


CONTRACT_MODELS: dict[str, type[BaseModel]] = {
    SESSION_LIFECYCLE_TOPIC: SessionLifecycleEvent,
    BEHAVIORAL_ACTIVITY_TOPIC: BehavioralActivityEvent,
    CV_FEATURES_TOPIC: CvFeatureWindowEvent,
    EFFORT_LABELS_TOPIC: EffortLabelEvent,
    PREDICTIONS_TOPIC: PredictionResultEvent,
    NOTIFICATIONS_TOPIC: NotificationEvent,
}


def contract_schema_filename(topic: str) -> str:
    if topic not in CONTRACT_MODELS:
        raise ValueError("unknown contract topic")
    return re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-") + ".json"
