"""FastAPI application for cognitive load pre/post-processing."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from cogniflow_data.api import router as event_router
from preprocessing_api.model_client import (
    predict_with_kserve,
    predict_with_local_model,
    verified_kserve_provenance,
    verified_local_model_provenance,
)
from preprocessing_api.observability import (
    CONTENT_TYPE_LATEST,
    MetricsMiddleware,
    configure_logging,
    configure_tracing,
    generate_latest,
    record_prediction,
)
from preprocessing_api.schemas import CognitiveLoadLevel, PredictionRequest, PredictionResponse
from preprocessing_api.security import SecurityMiddleware, is_production, require_api_key
from preprocessing_api.service import calculate_cognitive_load

configure_logging()
DEMO_HTML = (Path(__file__).with_name("static") / "index.html").read_text(encoding="utf-8")

app = FastAPI(
    title="Personal Cognitive Load Monitoring API",
    description=(
        "Pre/post-processing API for cognitive load prediction. The service validates "
        "focus/task signals and uses one explicitly configured inference backend."
    ),
    version="1.0.0",
    docs_url=None if is_production() else "/docs",
    redoc_url=None if is_production() else "/redoc",
    openapi_url=None if is_production() else "/openapi.json",
)
configure_tracing(app)
app.add_middleware(MetricsMiddleware)
app.add_middleware(SecurityMiddleware)
app.include_router(event_router)


@app.get("/")
async def root():
    """Serve the lightweight local demonstration."""
    return HTMLResponse(DEMO_HTML)


@app.get("/health")
async def health():
    """Liveness probe endpoint."""
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness probe endpoint."""
    mode = inference_mode()
    if mode == "local_model" and predict_with_local_model(PredictionRequest(
        focus_minutes=1, distraction_minutes=0, tasks_due=0, hours_to_deadline=168
    )) is None:
        raise HTTPException(status_code=503, detail="Configured local model is unavailable")
    if mode == "kserve":
        try:
            verified_kserve_provenance()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="KServe model is unavailable") from exc
    return {"status": "ready", "inference_mode": mode}


def inference_mode() -> str:
    mode = os.getenv("INFERENCE_MODE", "demo_rule")
    if mode not in {"demo_rule", "local_model", "kserve"}:
        raise RuntimeError("INFERENCE_MODE must be demo_rule, local_model, or kserve")
    return mode


@app.get("/model-info", dependencies=[Depends(require_api_key)])
async def model_info():
    mode = inference_mode()
    result = {
        "inference_mode": mode,
        "model_version": os.getenv("MODEL_VERSION") if mode != "demo_rule" else None,
        "label_provenance": "synthetic_proxy",
    }
    if mode == "local_model":
        provenance = verified_local_model_provenance()
        if provenance is None:
            raise HTTPException(status_code=503, detail="Verified model provenance is unavailable")
        result = {
            "inference_mode": mode,
            "model_version": provenance["model_version"],
            "label_provenance": provenance["label_provenance"],
            "model_name": provenance["model_name"],
            "dataset_sha256": provenance["dataset_sha256"],
            "feature_schema_version": provenance["feature_schema_version"],
            "feature_names": provenance["feature_names"],
            "registered_artifact_sha256": provenance["registered_artifact_sha256"],
            "packaged_model_sha256": provenance["packaged_model_sha256"],
            "run_id": provenance["run_id"],
            "git_revision": provenance["git_revision"],
        }
    elif mode == "kserve":
        try:
            provenance = verified_kserve_provenance()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Verified model provenance is unavailable") from exc
        result = {
            "inference_mode": mode,
            "model_version": provenance["model_version"],
            "label_provenance": provenance["label_provenance"],
            "model_name": provenance["model_name"],
            "dataset_sha256": provenance["dataset_sha256"],
            "feature_schema_version": provenance["feature_schema_version"],
            "feature_names": provenance["feature_names"],
            "registered_artifact_sha256": provenance["registered_artifact_sha256"],
            "packaged_model_sha256": provenance["packaged_model_sha256"],
            "run_id": provenance["run_id"],
            "git_revision": provenance["git_revision"],
        }
    return result


@app.get("/metrics")
async def metrics():
    """Prometheus scrape endpoint."""
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Return an empty favicon response to avoid 404 in logs."""
    return Response(status_code=204)


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    """Return a minimal robots.txt to avoid 404 in logs."""
    return Response(content="User-agent: *\nDisallow:\n", media_type="text/plain")


@app.post("/predict", response_model=PredictionResponse, dependencies=[Depends(require_api_key)])
async def predict(request: PredictionRequest) -> PredictionResponse:
    """Predict cognitive load from validated focus/task signals."""

    mode = inference_mode()
    cognitive_load_level: CognitiveLoadLevel | None
    if mode == "demo_rule":
        cognitive_load_level = calculate_cognitive_load(request)
        source = "demo_rule"
    elif mode == "local_model":
        cognitive_load_level = predict_with_local_model(request)
        source = "local_model"
        if cognitive_load_level is None:
            raise HTTPException(status_code=503, detail="Configured local model is unavailable")
    else:
        source = "kserve"
        try:
            cognitive_load_level = predict_with_kserve(request)
        except TimeoutError as exc:
            raise HTTPException(status_code=504, detail="Model server timed out") from exc
        except (ConnectionError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail="Model server is unavailable") from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Model server returned an invalid response") from exc

    if cognitive_load_level is None:
        raise HTTPException(status_code=503, detail="Configured inference backend is unavailable")
    record_prediction(cognitive_load_level.value, source)
    return PredictionResponse(
        cognitive_load_level=cognitive_load_level,
        inference_source=source,
        model_version=os.getenv("MODEL_VERSION") if mode != "demo_rule" else None,
        feature_as_of=request.feature_as_of,
        is_fallback=False,
    )


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})
