"""Pydantic schemas for request and response validation."""

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class CognitiveLoadLevel(str, Enum):
    """Cognitive load level enumeration."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PredictionRequest(BaseModel):
    """Request schema for cognitive load prediction."""

    focus_minutes: int = Field(..., ge=0, description="Minutes spent in focused work")
    distraction_minutes: int = Field(..., ge=0, description="Minutes spent distracted")
    tasks_due: int = Field(..., ge=0, description="Number of tasks due")
    hours_to_deadline: float = Field(..., ge=0.0, description="Hours until deadline")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "focus_minutes": 120,
                "distraction_minutes": 30,
                "tasks_due": 3,
                "hours_to_deadline": 24.0,
            }
        }
    )


class PredictionResponse(BaseModel):
    """Response schema for cognitive load prediction."""

    cognitive_load_level: CognitiveLoadLevel = Field(
        ..., description="Predicted cognitive load level"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cognitive_load_level": "MEDIUM",
            }
        }
    )

