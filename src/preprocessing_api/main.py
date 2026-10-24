"""FastAPI application for cognitive load pre/post-processing."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from preprocessing_api.model_client import (
    kserve_configured,
    kserve_reachable,
    local_model_available,
    predict_with_kserve,
    predict_with_local_model,
    read_model_manifest,
)
from preprocessing_api.observability import (
    CONTENT_TYPE_LATEST,
    configure_logging,
    configure_tracing,
    generate_latest,
    metrics_middleware,
    record_prediction,
)
from preprocessing_api.schemas import CognitiveLoadLevel, PredictionRequest, PredictionResponse
from preprocessing_api.service import calculate_cognitive_load

configure_logging()

VALID_INFERENCE_MODES = {"auto", "rule", "local_model", "kserve"}


def _read_inference_mode() -> str:
    """Read and validate INFERENCE_MODE at import time (fail fast on typos).

    - auto (default): try KServe, then the local model, then the rule
      fallback, in that order, silently. This preserves the existing local
      demo/CI behavior and is intentionally NOT recommended for a real
      deployment, because a caller cannot tell which backend answered a given
      request without reading response metrics.
    - rule / local_model / kserve: use exactly that backend. /predict returns
      503 instead of silently substituting a different backend when the
      selected one is unavailable, unless ALLOW_RULE_FALLBACK=true is set
      explicitly (see _resolve_prediction below).
    """

    mode = os.getenv("INFERENCE_MODE", "auto").strip().lower()
    if mode not in VALID_INFERENCE_MODES:
        raise RuntimeError(
            f"Invalid INFERENCE_MODE={mode!r}; must be one of {sorted(VALID_INFERENCE_MODES)}"
        )
    return mode


INFERENCE_MODE = _read_inference_mode()


def _allow_rule_fallback() -> bool:
    return os.getenv("ALLOW_RULE_FALLBACK", "false").strip().lower() in {"1", "true", "yes"}


app = FastAPI(
    title="Personal Cognitive Load Monitoring API",
    description=(
        "Pre/post-processing API for cognitive load prediction. Serves one of three "
        "explicit inference backends (rule, local_model, kserve) selected by "
        "INFERENCE_MODE, or the auto fallback chain used for local demos and tests. "
        "This is an educational MLOps demonstration, not a medical, psychological, "
        "neurological, workplace-surveillance, or diagnostic system."
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
    """Liveness probe endpoint: reports process liveness only, not backend readiness."""
    return {"status": "healthy"}


@app.get("/ready")
def ready():
    """Readiness probe endpoint.

    Reflects the actual health of the backend selected by INFERENCE_MODE:
    - rule: always ready (no external dependency).
    - local_model: ready only if the joblib artifact loads successfully.
    - kserve: ready only if KSERVE_PREDICT_URL is configured and a lightweight
      connectivity check succeeds (see model_client.kserve_reachable).
    - auto: always ready, since the rule fallback guarantees a response; use
      an explicit mode in production if you need readiness to reflect a
      specific backend's health.
    """

    if INFERENCE_MODE == "rule":
        is_ready = True
    elif INFERENCE_MODE == "local_model":
        is_ready = local_model_available()
    elif INFERENCE_MODE == "kserve":
        is_ready = kserve_reachable()
    else:  # auto
        is_ready = True

    body = {"status": "ready" if is_ready else "not_ready", "mode": INFERENCE_MODE}
    return JSONResponse(status_code=200 if is_ready else 503, content=body)


@app.get("/model-info")
def model_info():
    """Report which inference backend(s) are actually usable right now.

    Intentionally does not expose KSERVE_PREDICT_URL itself (internal
    endpoint) or any request data — only booleans and the model manifest
    written at build/download time, if any.
    """

    return {
        "inference_mode": INFERENCE_MODE,
        "allow_rule_fallback": _allow_rule_fallback(),
        "kserve_configured": kserve_configured(),
        "local_model_available": local_model_available(),
        "model_manifest": read_model_manifest(),
    }


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


def _resolve_prediction(request: PredictionRequest) -> tuple[CognitiveLoadLevel, str]:
    """Return (predicted_level, source) using the configured INFERENCE_MODE.

    In auto mode this silently chains kserve -> local_model -> rule, matching
    the project's local-demo/CI behavior. In an explicit mode, only that
    backend is used; if it fails, this raises HTTPException(503) unless
    ALLOW_RULE_FALLBACK=true, in which case it falls back to the rule engine
    with a visible "rule_fallback_after_error" source label rather than
    silently claiming the primary backend answered.
    """

    if INFERENCE_MODE == "rule":
        return calculate_cognitive_load(request), "rule"

    if INFERENCE_MODE == "local_model":
        prediction = predict_with_local_model(request)
        if prediction is not None:
            return prediction, "model_local"
        if _allow_rule_fallback():
            return calculate_cognitive_load(request), "rule_fallback_after_error"
        raise HTTPException(status_code=503, detail="Local model is not available (INFERENCE_MODE=local_model).")

    if INFERENCE_MODE == "kserve":
        prediction = predict_with_kserve(request)
        if prediction is not None:
            return prediction, "kserve"
        if _allow_rule_fallback():
            return calculate_cognitive_load(request), "rule_fallback_after_error"
        raise HTTPException(status_code=503, detail="KServe backend is not available (INFERENCE_MODE=kserve).")

    # auto: local demo / CI default, unchanged from prior behavior.
    prediction = predict_with_kserve(request)
    if prediction is not None:
        return prediction, "kserve"
    prediction = predict_with_local_model(request)
    if prediction is not None:
        return prediction, "model_local"
    return calculate_cognitive_load(request), "rule_fallback"


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    """Predict cognitive load from validated focus/task signals."""

    cognitive_load_level, source = _resolve_prediction(request)
    record_prediction(cognitive_load_level.value, source)
    return PredictionResponse(cognitive_load_level=cognitive_load_level)


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})
