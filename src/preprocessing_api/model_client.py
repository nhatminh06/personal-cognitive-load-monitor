"""Optional client for forwarding model inference to KServe.

The FastAPI service owns request validation and pre/post-processing. If a KServe
predictor URL is configured, the service forwards normalized features to KServe.
If KServe is not configured or is temporarily unavailable, the API falls back to
rule-based inference so the demo remains usable for local development.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from preprocessing_api.schemas import CognitiveLoadLevel, PredictionRequest

LOGGER = logging.getLogger(__name__)

_CLASS_MAP = {
    0: CognitiveLoadLevel.LOW,
    1: CognitiveLoadLevel.MEDIUM,
    2: CognitiveLoadLevel.HIGH,
    "0": CognitiveLoadLevel.LOW,
    "1": CognitiveLoadLevel.MEDIUM,
    "2": CognitiveLoadLevel.HIGH,
    "LOW": CognitiveLoadLevel.LOW,
    "MEDIUM": CognitiveLoadLevel.MEDIUM,
    "HIGH": CognitiveLoadLevel.HIGH,
}


def _feature_vector(request: PredictionRequest) -> list[float]:
    total_time = request.focus_minutes + request.distraction_minutes
    focus_ratio = request.focus_minutes / total_time if total_time else 0.0
    distraction_ratio = request.distraction_minutes / total_time if total_time else 0.0
    return [
        float(request.focus_minutes),
        float(request.distraction_minutes),
        float(request.tasks_due),
        float(request.hours_to_deadline),
        float(focus_ratio),
        float(distraction_ratio),
    ]


def kserve_payload(request: PredictionRequest) -> dict[str, list[list[float]]]:
    """Build a V1 inference payload accepted by common KServe sklearn servers."""

    return {"instances": [_feature_vector(request)]}


def _extract_prediction(payload: dict[str, Any]) -> CognitiveLoadLevel | None:
    predictions = payload.get("predictions") or payload.get("outputs")
    if predictions is None:
        return None

    first = predictions[0] if isinstance(predictions, list) and predictions else predictions
    if isinstance(first, list) and first:
        first = first[0]
    if isinstance(first, dict):
        first = first.get("class") or first.get("label") or first.get("prediction")

    return _CLASS_MAP.get(first)


def predict_with_kserve(request: PredictionRequest) -> CognitiveLoadLevel | None:
    """Call KServe when KSERVE_PREDICT_URL is configured.

    Returns None when KServe is disabled or unavailable, allowing the caller to
    use a deterministic fallback.
    """

    predict_url = os.getenv("KSERVE_PREDICT_URL")
    if not predict_url:
        return None

    try:
        import requests

        response = requests.post(
            predict_url,
            json=kserve_payload(request),
            timeout=float(os.getenv("KSERVE_TIMEOUT_SECONDS", "3")),
        )
        response.raise_for_status()
        prediction = _extract_prediction(response.json())
        if prediction is None:
            LOGGER.warning("KServe response did not contain a supported prediction: %s", response.text)
        return prediction
    except Exception as exc:  # pragma: no cover - network failure path
        LOGGER.warning("KServe prediction failed; using fallback. Error: %s", exc)
        return None
