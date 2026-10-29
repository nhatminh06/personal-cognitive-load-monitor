"""Strict versioned HTTP contracts for local focus inference."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cogniflow_contracts import EffortBand, effort_band


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FocusPredictionRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    window_id: UUID
    window_start: datetime
    window_end: datetime
    feature_cutoff: datetime
    behavioral_contract_version: Literal["1.0"] = "1.0"
    cv_contract_version: Literal["1.0"] | None = None
    cv_available: bool
    label_window_ids_used: tuple[UUID, ...] = ()

    @field_validator("window_start", "window_end", "feature_cutoff")
    @classmethod
    def utc_only(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("focus prediction timestamps must be UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def completed_unlabeled_window(self) -> Self:
        if self.window_end - self.window_start != timedelta(minutes=5):
            raise ValueError("focus prediction window must be exactly five minutes")
        if self.feature_cutoff != self.window_end:
            raise ValueError("feature_cutoff must equal window_end")
        if self.window_end > datetime.now(UTC):
            raise ValueError("focus prediction cannot use a future window")
        if self.cv_available != (self.cv_contract_version is not None):
            raise ValueError("CV availability and contract version are inconsistent")
        if self.label_window_ids_used:
            raise ValueError("focus prediction cannot accept label features")
        return self


class FocusPredictionResponse(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    prediction_id: UUID = Field(default_factory=uuid4)
    session_id: str
    window_id: UUID
    target_name: Literal["self_reported_effort"] = "self_reported_effort"
    target_version: Literal["self_reported_effort.v1"] = "self_reported_effort.v1"
    predicted_effort_rating: float = Field(ge=1, le=7, allow_inf_nan=False)
    effort_band: EffortBand
    model_name: str
    model_version: str
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    behavioral_contract_version: Literal["1.0"] = "1.0"
    cv_contract_version: Literal["1.0"] | None
    feature_cutoff: datetime
    cv_available: bool
    provenance_classification: Literal[
        "synthetic_fixture", "experimental_candidate", "approved_candidate"
    ]
    test_fixture: bool
    inference_source: Literal["local_focus_model"] = "local_focus_model"

    @model_validator(mode="after")
    def derived_values(self) -> Self:
        if self.effort_band != effort_band(self.predicted_effort_rating):
            raise ValueError("effort band does not match predicted rating")
        if self.cv_available != (self.cv_contract_version is not None):
            raise ValueError("CV response provenance is inconsistent")
        if self.test_fixture != (self.provenance_classification == "synthetic_fixture"):
            raise ValueError("test fixture status does not match package provenance")
        return self
