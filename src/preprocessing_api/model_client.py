"""Optional client for forwarding model inference to KServe.

The FastAPI service owns request validation and pre/post-processing. If a KServe
predictor URL is configured, the service forwards normalized features to KServe.
If KServe is not configured or is temporarily unavailable, the API falls back to
rule-based inference so the demo remains usable for local development.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from preprocessing_api.features import INVERSE_LABEL_MAP, feature_vector
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

# Derived from preprocessing_api.features.INVERSE_LABEL_MAP (the single source
# of truth also used by scripts/train_model.py), not a hand-copied duplicate.
_INVERSE_LABEL_MAP = {
    class_index: CognitiveLoadLevel(level_name) for class_index, level_name in INVERSE_LABEL_MAP.items()
}

_local_model: Any = None
_local_model_load_attempted = False


def kserve_payload(request: PredictionRequest) -> dict[str, list[list[float]]]:
    """Build a V1 inference payload accepted by common KServe sklearn servers."""

    return {"instances": [feature_vector(request)]}


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


def reset_local_model_cache() -> None:
    """Clear the cached local model so the next call reloads from disk. Test hook."""

    global _local_model, _local_model_load_attempted
    _local_model = None
    _local_model_load_attempted = False


def _load_local_model() -> Any:
    """Lazily load the joblib model trained by scripts/train_model.py, if present."""

    global _local_model, _local_model_load_attempted
    if _local_model_load_attempted:
        return _local_model

    _local_model_load_attempted = True
    model_path = Path(os.getenv("MODEL_PATH", "models/cognitive_load_model.joblib"))
    if not model_path.exists():
        return None

    try:
        import joblib

        _local_model = joblib.load(model_path)
    except Exception as exc:  # pragma: no cover - corrupt/incompatible artifact
        LOGGER.warning("Failed to load local model at %s: %s", model_path, exc)
        _local_model = None

    return _local_model


def read_model_manifest() -> dict[str, Any] | None:
    """Read the manifest scripts/download_model_from_mlflow.py writes alongside
    the model artifact, if present. Returns None (not an error) when no
    manifest exists, e.g. a fresh checkout with no model trained yet."""

    import json

    model_path = Path(os.getenv("MODEL_PATH", "models/cognitive_load_model.joblib"))
    manifest_path = model_path.with_suffix(model_path.suffix + ".manifest.json")
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - corrupt manifest is not fatal
        LOGGER.warning("Failed to read model manifest at %s: %s", manifest_path, exc)
        return None


def local_model_available() -> bool:
    """Whether the local joblib model can currently be loaded from MODEL_PATH.

    Used by /ready and /model-info so INFERENCE_MODE=local_model reports its
    real readiness state instead of always reporting healthy.
    """

    return _load_local_model() is not None


def kserve_configured() -> bool:
    """Whether KSERVE_PREDICT_URL is set. Does not check network reachability."""

    return bool(os.getenv("KSERVE_PREDICT_URL"))


def kserve_reachable(timeout_seconds: float = 2.0) -> bool:
    """Best-effort connectivity check against the configured KServe endpoint.

    This is a lightweight GET against the predictor host, not a guarantee that
    the model itself is healthy or that a POST /predict would succeed — a full
    synthetic-prediction health check would add latency and risk to every
    readiness probe tick. Returns False (not ready) on any error, including a
    missing KSERVE_PREDICT_URL.
    """

    predict_url = os.getenv("KSERVE_PREDICT_URL")
    if not predict_url:
        return False

    try:
        import requests

        response = requests.get(predict_url, timeout=timeout_seconds)
        # Any HTTP response (even 404/405 for a GET on a predict-only route)
        # means the endpoint is reachable; only network-level failures count
        # as "not ready".
        return response.status_code < 500
    except Exception as exc:  # pragma: no cover - network failure path
        LOGGER.warning("KServe readiness check failed: %s", exc)
        return False


def predict_with_local_model(request: PredictionRequest) -> CognitiveLoadLevel | None:
    """Run inference with the locally packaged joblib model, if one is available.

    Returns None when no model file is present or inference fails, allowing the
    caller to fall through to the deterministic rule-based fallback.
    """

    model = _load_local_model()
    if model is None:
        return None

    try:
        prediction = model.predict([feature_vector(request)])[0]
        return _INVERSE_LABEL_MAP.get(int(prediction))
    except Exception as exc:
        LOGGER.warning("Local model prediction failed; using fallback. Error: %s", exc)
        return None


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
