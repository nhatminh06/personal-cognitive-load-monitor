"""Versioned, privacy-minimal event contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from preprocessing_api.schemas import PredictionRequest

SESSION_TOPIC = "cogniflow.session-events.v1"
FEATURE_TOPIC = "cogniflow.features.v1"
DEAD_LETTER_TOPIC = "cogniflow.dead-letter.v1"


class EventProvenance(BaseModel):
    """Non-sensitive origin metadata carried with every event."""

    producer: str = Field(min_length=1, max_length=64)
    producer_version: str = Field(min_length=1, max_length=32)
    label_provenance: Literal["synthetic_proxy"] = "synthetic_proxy"

    model_config = ConfigDict(extra="forbid")


class SessionEvent(BaseModel):
    """Schema v1 session snapshot; event time is distinct from ingestion time."""

    event_id: UUID = Field(default_factory=uuid4)
    schema_version: Literal["1.0"] = "1.0"
    event_type: Literal["session.snapshot"] = "session.snapshot"
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    user_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Optional pseudonymous identifier; never an email or display name.",
    )
    event_time: datetime
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = Field(min_length=1, max_length=64)
    payload: PredictionRequest
    provenance: EventProvenance

    model_config = ConfigDict(extra="forbid")

    @field_validator("event_time", "ingested_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value

    def kafka_key(self) -> bytes:
        """Preserve ordering for snapshots from the same session."""

        return self.session_id.encode("utf-8")

    def wire_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


class EventAccepted(BaseModel):
    event_id: UUID
    topic: str
    accepted_at: datetime
    status: Literal["accepted"] = "accepted"
