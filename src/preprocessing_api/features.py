"""Shared training and serving feature contract."""

from __future__ import annotations

from collections.abc import Mapping

FEATURE_NAMES = (
    "focus_minutes",
    "distraction_minutes",
    "tasks_due",
    "hours_to_deadline",
    "focus_ratio",
    "distraction_ratio",
)


def feature_vector(values: Mapping[str, int | float]) -> list[float]:
    """Return the canonical, ordered model input vector."""
    focus = float(values["focus_minutes"])
    distraction = float(values["distraction_minutes"])
    total = focus + distraction
    return [
        focus,
        distraction,
        float(values["tasks_due"]),
        float(values["hours_to_deadline"]),
        focus / total if total else 0.0,
        distraction / total if total else 0.0,
    ]
