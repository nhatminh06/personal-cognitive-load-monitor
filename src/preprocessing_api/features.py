"""Canonical feature engineering shared by training and serving.

Both ``scripts/train_model.py`` (training) and ``preprocessing_api.model_client``
(serving) must derive identical feature vectors, in identical column order, from
the same raw fields. Before this module existed, the column list and the
focus/distraction-ratio formula were copy-pasted in both places with only a
comment ("Mirrors LABEL_MAP...") reminding a future editor to keep them in
sync. A silent mismatch here is training-serving skew: the model would receive
features in a different order than it was trained on and produce meaningless
predictions without raising any error.
"""

from __future__ import annotations

from preprocessing_api.schemas import PredictionRequest

FEATURE_COLUMNS = [
    "focus_minutes",
    "distraction_minutes",
    "tasks_due",
    "hours_to_deadline",
    "focus_ratio",
    "distraction_ratio",
]

LABEL_MAP = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
INVERSE_LABEL_MAP = {value: key for key, value in LABEL_MAP.items()}


def focus_and_distraction_ratios(focus_minutes: float, distraction_minutes: float) -> tuple[float, float]:
    """Return (focus_ratio, distraction_ratio); both 0.0 when total time is 0."""

    total_time = focus_minutes + distraction_minutes
    if not total_time:
        return 0.0, 0.0
    return focus_minutes / total_time, distraction_minutes / total_time


def feature_vector(request: PredictionRequest) -> list[float]:
    """Build the feature vector for a single request, in FEATURE_COLUMNS order."""

    focus_ratio, distraction_ratio = focus_and_distraction_ratios(
        request.focus_minutes, request.distraction_minutes
    )
    return [
        float(request.focus_minutes),
        float(request.distraction_minutes),
        float(request.tasks_due),
        float(request.hours_to_deadline),
        float(focus_ratio),
        float(distraction_ratio),
    ]
