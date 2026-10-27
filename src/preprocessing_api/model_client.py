"""Local-model and KServe inference clients."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
from numbers import Integral
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from preprocessing_api.features import FEATURE_NAMES, feature_vector
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
_local_model_provenance: dict[str, Any] | None = None
_ZERO_SHA256 = "0" * 64


def kserve_payload(request: PredictionRequest) -> dict[str, list[list[float]]]:
    """Build a V1 inference payload accepted by common KServe sklearn servers."""

    return {"instances": [feature_vector(request.model_dump())]}


def _extract_prediction(payload: dict[str, Any]) -> CognitiveLoadLevel:
    predictions = payload.get("predictions")
    if not isinstance(predictions, list) or len(predictions) != 1:
        raise ValueError("KServe must return exactly one prediction")
    return _validated_class(predictions[0])


def reset_local_model_cache() -> None:
    """Clear the cached local model so the next call reloads from disk. Test hook."""

    global _local_model, _local_model_load_attempted, _local_model_provenance
    _local_model = None
    _local_model_load_attempted = False
    _local_model_provenance = None


def _validated_class(value: Any) -> CognitiveLoadLevel:
    if isinstance(value, bool) or not isinstance(value, (Integral, str)):
        raise ValueError("model returned an unsupported prediction class")
    result = _CLASS_MAP.get(int(value) if isinstance(value, Integral) else value)
    if result is None:
        raise ValueError("model returned an unknown prediction class")
    return result


def validated_package_manifest(model_path: Path, actual_digest: str) -> dict[str, Any]:
    manifest_path = Path(os.getenv("MODEL_PACKAGE_PATH", model_path.with_name("model-package.json")))
    manifest = json.loads(manifest_path.read_text())
    required = {
        "contract_version", "approval_status", "model_name", "model_version", "registered_artifact_sha256",
        "packaged_model_sha256", "dataset_sha256", "feature_schema_version", "feature_names",
        "label_provenance", "run_id", "registered_source", "git_revision", "approved_by",
        "approved_at",
    }
    if not required <= manifest.keys():
        raise ValueError("model package manifest is incomplete")
    expected = {
        "model_name": os.getenv("MODEL_NAME", ""),
        "model_version": os.getenv("MODEL_VERSION", ""),
        "registered_artifact_sha256": os.getenv("MODEL_ARTIFACT_SHA256", ""),
        "dataset_sha256": os.getenv("MODEL_DATASET_SHA256", ""),
        "feature_schema_version": os.getenv("MODEL_FEATURE_SCHEMA_VERSION", ""),
        "packaged_model_sha256": os.getenv("MODEL_SHA256", ""),
    }
    if any(not value or str(manifest[name]) != value for name, value in expected.items()):
        raise ValueError("model package manifest does not match deployment configuration")
    if (
        manifest["contract_version"] != "1.0"
        or manifest["approval_status"] != "approved"
        or manifest["feature_schema_version"] != "1.0"
        or manifest["feature_names"] != list(FEATURE_NAMES)
        or manifest["label_provenance"] != "synthetic_proxy"
        or not re.fullmatch(r"[a-f0-9]{64}", manifest["registered_artifact_sha256"])
        or not re.fullmatch(r"[a-f0-9]{64}", manifest["dataset_sha256"])
        or not re.fullmatch(r"[a-f0-9]{40}", manifest["git_revision"])
        or not manifest["approved_by"]
        or not manifest["approved_at"]
    ):
        raise ValueError("model package manifest contract is invalid")
    if not hmac.compare_digest(manifest["packaged_model_sha256"], actual_digest):
        raise ValueError("packaged model digest does not match manifest")
    return manifest


_validated_package_manifest = validated_package_manifest


def _expected_kserve_provenance() -> dict[str, str]:
    expected = {
        "model_name": os.getenv("MODEL_NAME", ""),
        "model_version": os.getenv("MODEL_VERSION", ""),
        "registered_artifact_sha256": os.getenv("MODEL_ARTIFACT_SHA256", ""),
        "packaged_model_sha256": os.getenv("MODEL_SHA256", ""),
        "dataset_sha256": os.getenv("MODEL_DATASET_SHA256", ""),
        "feature_schema_version": os.getenv("MODEL_FEATURE_SCHEMA_VERSION", ""),
    }
    if any(not value for value in expected.values()):
        raise RuntimeError("KServe expected provenance is incomplete")
    if (
        not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", expected["model_name"])
        or not re.fullmatch(r"[1-9][0-9]*", expected["model_version"])
        or any(
            not re.fullmatch(r"[a-f0-9]{64}", expected[name])
            or expected[name] == _ZERO_SHA256
            for name in (
                "registered_artifact_sha256",
                "packaged_model_sha256",
                "dataset_sha256",
            )
        )
        or expected["feature_schema_version"] != "1.0"
    ):
        raise RuntimeError("KServe expected provenance contains placeholder or invalid values")
    return expected


def _validated_kserve_url(name: str, expected_suffix: str) -> str:
    value = os.getenv(name, "")
    allowed_origin = os.getenv("KSERVE_ALLOWED_ORIGIN", "")
    parsed, allowed = urlsplit(value), urlsplit(allowed_origin)
    if (
        not value
        or parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or allowed.scheme != "http"
        or not allowed.hostname
        or allowed.path not in {"", "/"}
        or allowed.query
        or allowed.fragment
        or (parsed.scheme, parsed.netloc) != (allowed.scheme, allowed.netloc)
        or parsed.path != expected_suffix
    ):
        raise RuntimeError(f"{name} must use the explicit trusted KServe origin and path")
    return value


def _validate_kserve_provenance(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("KServe provenance response is malformed")
    expected = _expected_kserve_provenance()
    if any(str(payload.get(name, "")) != value for name, value in expected.items()):
        raise ValueError("KServe provenance does not match deployment configuration")
    if payload.get("feature_names") != list(FEATURE_NAMES) or payload.get("label_provenance") != "synthetic_proxy":
        raise ValueError("KServe provenance contract is incompatible")
    return payload


def _kserve_timeout() -> float:
    try:
        value = float(os.getenv("KSERVE_TIMEOUT_SECONDS", "3"))
    except ValueError as exc:
        raise RuntimeError("KSERVE_TIMEOUT_SECONDS must be a finite number") from exc
    if not math.isfinite(value) or not 0 < value <= 30:
        raise RuntimeError("KSERVE_TIMEOUT_SECONDS must be greater than zero and at most 30")
    return value


async def _kserve_request(method: str, url: str, **kwargs: Any) -> Any:
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=_kserve_timeout(), follow_redirects=False, trust_env=False
        ) as client:
            response = await client.request(method, url, **kwargs)
    except httpx.TimeoutException as exc:
        raise TimeoutError("KServe request timed out") from exc
    except httpx.RequestError as exc:
        raise ConnectionError("KServe request failed") from exc
    if 300 <= response.status_code < 400:
        raise ValueError("KServe redirect rejected")
    if response.status_code >= 500:
        raise ConnectionError("KServe service is unavailable")
    if response.status_code >= 400:
        raise ValueError("KServe returned an invalid HTTP response")
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError("KServe returned invalid JSON") from exc


async def verified_kserve_provenance() -> dict[str, Any]:

    model_name = os.getenv("MODEL_NAME", "")
    url = _validated_kserve_url(
        "KSERVE_METADATA_URL", f"/v1/models/{model_name}/metadata"
    )
    return _validate_kserve_provenance(await _kserve_request("GET", url))


def verified_local_model_provenance() -> dict[str, Any] | None:
    """Return provenance only after the packaged model passes every loading check."""

    _load_local_model()
    return _local_model_provenance


def _load_local_model() -> Any:
    """Lazily load the joblib model trained by scripts/train_model.py, if present."""

    global _local_model, _local_model_load_attempted, _local_model_provenance
    if _local_model_load_attempted:
        return _local_model

    _local_model_load_attempted = True
    model_path = Path(os.getenv("MODEL_PATH", "models/cognitive_load_model.joblib"))
    if not model_path.exists():
        return None

    expected_digest = os.getenv("MODEL_SHA256", "").strip().lower()
    if is_production() and not expected_digest:
        LOGGER.error("MODEL_SHA256 is required before production local-model loading")
        return None
    try:
        actual_digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if expected_digest and not hmac.compare_digest(actual_digest, expected_digest):
            LOGGER.error("Local model digest verification failed")
            return None
        if model_path.suffix == ".skops":
            import skops.io

            _local_model_provenance = validated_package_manifest(model_path, actual_digest)
            _local_model = skops.io.load(model_path, trusted=_SKOPS_TRUSTED_TYPES)
        elif model_path.suffix in {".joblib", ".pkl"}:
            import joblib

            _local_model = joblib.load(model_path)
        else:
            raise ValueError("unsupported local model format")
    except Exception:  # pragma: no cover - corrupt/incompatible artifact
        LOGGER.warning("Trusted local model could not be loaded")
        _local_model = None
        _local_model_provenance = None

    return _local_model


def predict_with_local_model(request: PredictionRequest) -> CognitiveLoadLevel | None:
    """Run inference with a digest-verified local model, if one is available.

    Returns None when loading, provenance verification, or inference fails. The
    local_model API mode treats None as unavailable and never falls back.
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


async def predict_with_kserve(request: PredictionRequest) -> CognitiveLoadLevel:
    """Call KServe when KSERVE_PREDICT_URL is configured.

    Raises a bounded error when KServe is unavailable; production callers must
    never conceal that outage with a different predictor.
    """

    model_name = os.getenv("MODEL_NAME", "")
    predict_url = _validated_kserve_url("KSERVE_PREDICT_URL", f"/v1/models/{model_name}:predict")

    payload = await _kserve_request("POST", predict_url, json=kserve_payload(request))
    if not isinstance(payload, dict) or set(payload) != {"predictions", "provenance"}:
        raise ValueError("KServe returned an unsupported prediction payload")
    _validate_kserve_provenance(payload["provenance"])
    return _extract_prediction(payload)
