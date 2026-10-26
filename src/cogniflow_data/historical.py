"""Point-in-time historical feature and training-data contracts."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from preprocessing_api.features import FEATURE_NAMES, feature_vector

FEATURE_SCHEMA_VERSION = "1.0"
SILVER_DATASET = "s3a://cogniflow-lakehouse/silver/session_features"
SYNTHETIC_DATASET = "synthetic://cogniflow/module3-training-v1"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("event_time", "ingested_at", "decision_time", "available_at", check_fields=False)
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)


class SourceSnapshot(StrictContract):
    dataset: Literal["s3a://cogniflow-lakehouse/silver/session_features"] = (
        "s3a://cogniflow-lakehouse/silver/session_features"
    )
    delta_version: int = Field(ge=0)
    committed_at: datetime

    @field_validator("committed_at")
    @classmethod
    def committed_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value.astimezone(UTC)


class SilverFeatureEvent(StrictContract):
    event_id: UUID
    session_id: str = Field(min_length=1, max_length=128)
    schema_version: Literal["1.0"]
    event_time: datetime
    ingested_at: datetime
    source: str = Field(min_length=1)
    focus_minutes: int = Field(ge=0, le=1440)
    distraction_minutes: int = Field(ge=0, le=1440)
    tasks_due: int = Field(ge=0, le=1000)
    hours_to_deadline: float = Field(ge=0, le=87600, allow_inf_nan=False)
    focus_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    distraction_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    kafka_topic: str = Field(min_length=1)
    kafka_partition: int = Field(ge=0)
    kafka_offset: int = Field(ge=0)

    @model_validator(mode="after")
    def ratios_match_contract(self) -> SilverFeatureEvent:
        expected = feature_vector(self.model_dump())[-2:]
        actual = (self.focus_ratio, self.distraction_ratio)
        if any(not math.isclose(a, e, abs_tol=1e-12) for a, e in zip(actual, expected)):
            raise ValueError("ratios do not match feature contract")
        return self


class FeatureDecision(StrictContract):
    decision_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    decision_time: datetime


class HistoricalFeatureRow(StrictContract):
    decision_id: str
    session_id: str
    event_id: UUID
    feature_schema_version: Literal["1.0"]
    feature_names: tuple[str, ...] = FEATURE_NAMES
    event_time: datetime
    ingested_at: datetime
    decision_time: datetime
    available_at: datetime
    source_dataset: Literal[
        "s3a://cogniflow-lakehouse/silver/session_features",
        "synthetic://cogniflow/module3-training-v1",
    ]
    source_delta_version: int | None = Field(default=None, ge=0)
    source: str
    kafka_topic: str
    kafka_partition: int
    kafka_offset: int
    focus_minutes: int = Field(ge=0, le=1440)
    distraction_minutes: int = Field(ge=0, le=1440)
    tasks_due: int = Field(ge=0, le=1000)
    hours_to_deadline: float = Field(ge=0, le=87600, allow_inf_nan=False)
    focus_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    distraction_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def lineage_matches_source(self) -> HistoricalFeatureRow:
        if self.feature_names != FEATURE_NAMES:
            raise ValueError("feature names must use the canonical order")
        if self.source_dataset == SILVER_DATASET and self.source_delta_version is None:
            raise ValueError("Delta-backed features require a source version")
        if self.source_dataset == SYNTHETIC_DATASET and self.source_delta_version is not None:
            raise ValueError("synthetic features must not claim Delta provenance")
        if not self.event_time <= self.ingested_at <= self.available_at <= self.decision_time:
            raise ValueError("feature timestamps violate point-in-time ordering")
        expected = feature_vector(self.model_dump())[-2:]
        if any(
            not math.isclose(actual, wanted, abs_tol=1e-12)
            for actual, wanted in zip((self.focus_ratio, self.distraction_ratio), expected)
        ):
            raise ValueError("ratios do not match feature contract")
        return self

    def ordered_features(self) -> list[float]:
        return feature_vector(self.model_dump())


class SyntheticLabel(StrictContract):
    decision_id: str = Field(min_length=1)
    label: Literal["LOW", "MEDIUM", "HIGH"]
    event_time: datetime
    available_at: datetime
    provenance: Literal["synthetic_proxy"] = "synthetic_proxy"

    @model_validator(mode="after")
    def availability_follows_event(self) -> SyntheticLabel:
        if self.available_at < self.event_time:
            raise ValueError("label availability precedes its event")
        return self


def _deduplicate(events: list[SilverFeatureEvent]) -> list[SilverFeatureEvent]:
    unique: dict[UUID, SilverFeatureEvent] = {}
    for event in events:
        previous = unique.get(event.event_id)
        if previous is not None and previous != event:
            raise ValueError(f"conflicting duplicate event_id: {event.event_id}")
        unique[event.event_id] = event
    return list(unique.values())


def select_historical_features(
    events: list[SilverFeatureEvent],
    decisions: list[FeatureDecision],
    snapshot: SourceSnapshot,
) -> list[HistoricalFeatureRow]:
    """Select the latest event known by each decision time without future leakage."""

    unique = _deduplicate(events)
    decision_ids = [decision.decision_id for decision in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("decision_id values must be unique")
    output: list[HistoricalFeatureRow] = []
    for decision in sorted(decisions, key=lambda item: item.decision_id):
        eligible = [
            event
            for event in unique
            if event.session_id == decision.session_id
            and event.event_time <= decision.decision_time
            and event.ingested_at <= decision.decision_time
        ]
        if not eligible:
            continue
        selected = max(eligible, key=lambda item: (item.event_time, item.ingested_at, str(item.event_id)))
        values = selected.model_dump()
        output.append(
            HistoricalFeatureRow(
                decision_id=decision.decision_id,
                session_id=selected.session_id,
                event_id=selected.event_id,
                feature_schema_version=selected.schema_version,
                event_time=selected.event_time,
                ingested_at=selected.ingested_at,
                decision_time=decision.decision_time,
                available_at=selected.ingested_at,
                source_dataset=snapshot.dataset,
                source_delta_version=snapshot.delta_version,
                source=selected.source,
                kafka_topic=selected.kafka_topic,
                kafka_partition=selected.kafka_partition,
                kafka_offset=selected.kafka_offset,
                **{name: values[name] for name in FEATURE_NAMES},
            )
        )
    return output


def available_labels(labels: list[SyntheticLabel], cutoff: datetime) -> dict[str, SyntheticLabel]:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("label cutoff must include a timezone")
    eligible = (label for label in labels if label.available_at <= cutoff.astimezone(UTC))
    return {label.decision_id: label for label in sorted(eligible, key=lambda item: (item.available_at, item.decision_id))}


def write_dataset(
    rows: list[HistoricalFeatureRow], output: Path, metadata: Path, *, code_revision: str
) -> dict[str, object]:
    payload = "".join(row.model_dump_json() + "\n" for row in rows).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    manifest: dict[str, object] = {
        "contract_version": "1.0",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": list(FEATURE_NAMES),
        "source_dataset": SILVER_DATASET,
        "source_delta_versions": sorted(
            {row.source_delta_version for row in rows if row.source_delta_version is not None}
        ),
        "code_revision": code_revision,
        "selection": "event_time<=decision_time AND ingested_at<=decision_time",
        "row_count": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "quality": {
            "validation": "passed",
            "selected_rows": len(rows),
            "duplicate_policy": "collapse identical event IDs; reject conflicts",
        },
    }
    metadata.parent.mkdir(parents=True, exist_ok=True)
    metadata.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
