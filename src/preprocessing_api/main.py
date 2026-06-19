"""FastAPI application for cognitive load pre/post-processing."""

from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from preprocessing_api.model_client import predict_with_kserve
from preprocessing_api.observability import (
    CONTENT_TYPE_LATEST,
    configure_logging,
    configure_tracing,
    generate_latest,
    metrics_middleware,
    record_prediction,
)
from preprocessing_api.schemas import PredictionRequest, PredictionResponse
from preprocessing_api.service import calculate_cognitive_load

configure_logging()

app = FastAPI(
    title="Personal Cognitive Load Monitoring API",
    description=(
        "Pre/post-processing API for cognitive load prediction. The service validates "
        "focus/task signals, forwards to KServe when configured, and falls back to "
        "deterministic rule-based inference for local demos."
    ),
    version="1.0.0",
)
app.middleware("http")(metrics_middleware)
configure_tracing(app)


@app.get("/")
def root():
    """Basic service metadata endpoint."""
    return {"status": "healthy", "service": "cognitive-load-monitor"}


@app.get("/health")
def health():
    """Liveness probe endpoint."""
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    """Readiness probe endpoint."""
    return {"status": "ready"}


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Return an empty favicon response to avoid 404 in logs."""
    return Response(status_code=204)


@app.get("/robots.txt", include_in_schema=False)
def robots():
    """Return a minimal robots.txt to avoid 404 in logs."""
    return Response(content="User-agent: *\nDisallow:\n", media_type="text/plain")


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    """Predict cognitive load from validated focus/task signals."""

    prediction = predict_with_kserve(request)
    source = "kserve" if prediction is not None else "rule_fallback"
    cognitive_load_level = prediction or calculate_cognitive_load(request)
    record_prediction(cognitive_load_level.value, source)
    return PredictionResponse(cognitive_load_level=cognitive_load_level)


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})
