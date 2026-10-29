"""Authenticated local focus-session inference routes."""

from __future__ import annotations

import asyncio
import os
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException

from cogniflow_contracts import BehavioralActivityEvent, CvFeatureWindowEvent, effort_band
from cogniflow_data.multimodal import BEHAVIORAL_FEATURES, CV_FEATURES
from cogniflow_sessions import FocusSessionRepository, NotFoundError
from preprocessing_api.security import authenticated_owner
from preprocessing_api.sessions import get_session_repository

from .runtime import FocusModelRuntime
from .schemas import FocusPredictionRequest, FocusPredictionResponse

router = APIRouter(prefix="/v1/focus", tags=["focus-inference"])
_inference_slots = asyncio.Semaphore(4)


@lru_cache(maxsize=1)
def get_focus_runtime() -> FocusModelRuntime:
    path = Path(os.getenv("FOCUS_MODEL_PACKAGE_PATH", "models/focus-unavailable"))
    allow_fixture = os.getenv("FOCUS_MODEL_TEST_MODE", "false").lower() == "true"
    runtime = FocusModelRuntime(path, allow_synthetic_fixture=allow_fixture)
    runtime.load()
    return runtime


def reset_focus_runtime() -> None:
    get_focus_runtime.cache_clear()


def _stored_features(record: dict, feature_names: tuple[str, ...]) -> tuple[dict, bool]:
    activity = BehavioralActivityEvent.model_validate(record["activity"])
    cv = CvFeatureWindowEvent.model_validate(record["cv"]) if record["cv"] else None
    cv_available = bool(cv is not None and cv.camera_available)
    values = {name: getattr(activity, name) for name in BEHAVIORAL_FEATURES}
    cv_values = {
        name: getattr(cv, name) if cv_available and cv is not None else None
        for name in CV_FEATURES if name != "frame_drop_ratio"
    }
    cv_values["frame_drop_ratio"] = (
        cv.frames_dropped / cv.frames_sampled
        if cv_available and cv is not None and cv.frames_sampled else None
    )
    values.update(cv_values)
    values["cv_available"] = int(cv_available)
    return {name: values[name] for name in feature_names}, cv_available


@router.get("/health")
async def focus_health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/ready")
async def focus_ready() -> dict[str, str]:
    try:
        runtime = get_focus_runtime()
    except Exception as exc:
        raise HTTPException(503, "Focus model is unavailable") from exc
    if not runtime.ready:
        raise HTTPException(503, "Focus model is unavailable")
    return {"status": "ready"}


@router.post("/predict", response_model=FocusPredictionResponse)
async def focus_predict(
    request: FocusPredictionRequest,
    owner: str = Depends(authenticated_owner),
    repository: FocusSessionRepository = Depends(get_session_repository),
) -> FocusPredictionResponse:
    try:
        record = repository.feature_window(request.session_id, request.window_id, owner)
    except NotFoundError as exc:
        raise HTTPException(404, "Completed focus window is unavailable") from exc
    window = record["window"]
    if (
        window["window_start"] != request.window_start.isoformat()
        or window["window_end"] != request.window_end.isoformat()
    ):
        raise HTTPException(409, "Focus window boundaries do not match stored data")
    try:
        runtime = get_focus_runtime()
        if runtime.manifest is None:
            raise RuntimeError("focus model is not ready")
        features, cv_available = _stored_features(record, runtime.manifest.feature_names)
        if request.cv_available != cv_available:
            raise HTTPException(409, "CV availability does not match stored data")
        if runtime.manifest.modality == "B" and not cv_available:
            raise HTTPException(422, "Configured focus model requires available CV features")
        async with _inference_slots:
            rating = await asyncio.to_thread(runtime.predict, features)
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, "Focus model is unavailable") from exc
    manifest = runtime.manifest
    return FocusPredictionResponse(
        session_id=request.session_id, window_id=request.window_id,
        predicted_effort_rating=rating, effort_band=effort_band(rating),
        model_name=manifest.model_name, model_version=manifest.model_version,
        package_sha256=manifest.package_sha256,
        cv_contract_version="1.0" if cv_available else None,
        feature_cutoff=request.feature_cutoff, cv_available=cv_available,
        provenance_classification=manifest.provenance_classification,
        test_fixture=manifest.provenance_classification == "synthetic_fixture",
    )
