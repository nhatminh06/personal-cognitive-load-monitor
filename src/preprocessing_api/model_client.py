"""Local-model and KServe inference clients."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from numbers import Integral
from pathlib import Path
from typing import Any

from preprocessing_api.features import feature_vector
from preprocessing_api.schemas import CognitiveLoadLevel, PredictionRequest
from preprocessing_api.security import is_production

LOGGER = logging.getLogger(__name__)

# Phase I models use encoded integers; Phase II models emit canonical string labels.
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

_SKOPS_TRUSTED_TYPES = ["sklearn.tree._tree.Tree"]

_local_model: Any = None
_local_model_load_attempted = False


def kserve_payload(request: PredictionRequest) -> dict[str, list[list[float]]]:
    """Build a V1 inference payload accepted by common KServe sklearn servers."""

    return {"instances": [feature_vector(request.model_dump())]}


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


def _validated_class(value: Any) -> CognitiveLoadLevel:
    if isinstance(value, bool) or not isinstance(value, (Integral, str)):
        raise ValueError("model returned an unsupported prediction class")
    result = _CLASS_MAP.get(int(value) if isinstance(value, Integral) else value)
    if result is None:
        raise ValueError("model returned an unknown prediction class")
    return result


def _load_local_model() -> Any:
    """Lazily load the joblib model trained by scripts/train_model.py, if present."""

    global _local_model, _local_model_load_attempted
    if _local_model_load_attempted:
        return _local_model

    _local_model_load_attempted = True
    model_path = Path(os.getenv("MODEL_PATH", "models/cognitive_load_model.joblib"))
    if not model_path.exists():
        return None

    expected_digest = os.getenv("MODEL_SHA256", "").strip().lower()
    if is_production() and not expected_digest:
        LOGGER.error("MODEL_SHA256 is required before production joblib loading")
        return None
    if expected_digest:
        actual_digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            LOGGER.error("Local model digest verification failed")
            return None

    try:
        if model_path.suffix == ".skops":
            import skops.io

            _local_model = skops.io.load(model_path, trusted=_SKOPS_TRUSTED_TYPES)
        elif model_path.suffix in {".joblib", ".pkl"}:
            import joblib

            _local_model = joblib.load(model_path)
        else:
            raise ValueError("unsupported local model format")
    except Exception:  # pragma: no cover - corrupt/incompatible artifact
        LOGGER.warning("Trusted local model could not be loaded")
        _local_model = None

    return _local_model


def predict_with_local_model(request: PredictionRequest) -> CognitiveLoadLevel | None:
    """Run inference with the locally packaged joblib model, if one is available.

    Returns None when no model file is present or inference fails, allowing the
    caller to fall through to the deterministic rule-based fallback.
    """

    model = _load_local_model()
    if model is None:
        return None

    try:
        prediction = model.predict([feature_vector(request.model_dump())])[0]
        return _validated_class(prediction)
    except Exception:
        LOGGER.warning("Local model prediction failed; backend unavailable")
        return None


def predict_with_kserve(request: PredictionRequest) -> CognitiveLoadLevel | None:
    """Call KServe when KSERVE_PREDICT_URL is configured.

    Raises a bounded error when KServe is unavailable; production callers must
    never conceal that outage with a different predictor.
    """

    predict_url = os.getenv("KSERVE_PREDICT_URL")
    if not predict_url:
        raise RuntimeError("KSERVE_PREDICT_URL is required in kserve mode")

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
            raise ValueError("KServe returned an unsupported prediction payload")
        return prediction
    except (RuntimeError, ValueError):
        raise
    except Exception as exc:  # pragma: no cover - exercised through mocked request failures
        raise ConnectionError("KServe prediction failed") from exc
