"""Shared online/offline behavioral feature projection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cogniflow_contracts import BehavioralActivityEvent


class BehavioralFeatureRecord(BaseModel):
    feature_schema_version: str = "1.0"
    session_id: str
    window_id: UUID
    window_start: datetime
    window_end: datetime
    feature_cutoff: datetime
    source_event_id: UUID
    source: str
    active_seconds: float = Field(ge=0, le=300)
    idle_seconds: float = Field(ge=0, le=300)
    keyboard_event_count: int = Field(ge=0)
    pointer_event_count: int = Field(ge=0)
    application_switch_count: int = Field(ge=0)
    build_count: int | None = Field(default=None, ge=0)
    test_count: int | None = Field(default=None, ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)


def behavioral_features(event: BehavioralActivityEvent) -> BehavioralFeatureRecord:
    """Project only observed activity fields; absent optional counts remain absent."""

    return BehavioralFeatureRecord(
        session_id=event.session_id,
        window_id=event.window_id,
        window_start=event.window_start,
        window_end=event.window_end,
        feature_cutoff=event.feature_cutoff,
        source_event_id=event.event_id,
        source=f"{event.source}:cogniflow.behavioral-activity.v1",
        active_seconds=event.active_seconds,
        idle_seconds=event.idle_seconds,
        keyboard_event_count=event.keyboard_event_count,
        pointer_event_count=event.pointer_event_count,
        application_switch_count=event.application_switch_count,
        build_count=event.build_count,
        test_count=event.test_count,
    )


def replay_behavioral_features(
    events: list[BehavioralActivityEvent],
) -> list[BehavioralFeatureRecord]:
    """Deduplicate immutable raw events and return deterministic window order."""

    by_event: dict[UUID, BehavioralActivityEvent] = {}
    by_window: dict[UUID, BehavioralActivityEvent] = {}
    for event in events:
        if event.event_id in by_event and by_event[event.event_id] != event:
            raise ValueError(f"conflicting duplicate event_id: {event.event_id}")
        if event.window_id in by_window and by_window[event.window_id] != event:
            raise ValueError(f"conflicting duplicate window_id: {event.window_id}")
        by_event[event.event_id] = event
        by_window[event.window_id] = event
    return [
        behavioral_features(event)
        for event in sorted(by_window.values(), key=lambda item: (item.window_end, str(item.window_id)))
    ]
