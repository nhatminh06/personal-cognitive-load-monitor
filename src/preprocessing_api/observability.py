"""Small observability helpers for metrics, logging, and tracing."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

LOGGER = logging.getLogger(__name__)

try:  # Optional dependency so tests can run even in minimal environments.
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
except Exception:  # pragma: no cover - import fallback
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"
    Counter = Histogram = None

    def generate_latest() -> bytes:
        return b"# prometheus_client is not installed\n"


REQUEST_COUNT = (
    Counter(
        "cognitive_load_api_requests_total",
        "Total HTTP requests handled by the API.",
        ["method", "endpoint", "http_status"],
    )
    if Counter
    else None
)

REQUEST_LATENCY = (
    Histogram(
        "cognitive_load_api_request_duration_seconds",
        "HTTP request latency in seconds.",
        ["method", "endpoint"],
    )
    if Histogram
    else None
)

PREDICTION_COUNT = (
    Counter(
        "cognitive_load_predictions_total",
        "Total predictions by level and source.",
        ["level", "source"],
    )
    if Counter
    else None
)


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def configure_tracing(app) -> None:
    """Attach OpenTelemetry FastAPI instrumentation when installed.

    Tracing only activates when an OTLP endpoint is explicitly configured.
    Without this guard, ENABLE_TRACING defaults to "true" and the exporter
    falls back to localhost:4317, which is almost never running in local dev,
    CI, or `pytest` -- it just retries in the background and spams stderr
    with "connection refused" errors on every test run and app shutdown.
    """

    if os.getenv("ENABLE_TRACING", "true").lower() not in {"1", "true", "yes"}:
        return

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        LOGGER.info("OTEL_EXPORTER_OTLP_ENDPOINT not set; tracing disabled for this run.")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "cognitive-load-api")})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # pragma: no cover - optional instrumentation
        LOGGER.warning("OpenTelemetry tracing is disabled: %s", exc)


async def metrics_middleware(request, call_next: Callable):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    endpoint = request.scope.get("route").path if request.scope.get("route") else request.url.path

    if REQUEST_COUNT:
        REQUEST_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()
    if REQUEST_LATENCY:
        REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)

    return response


def record_prediction(level: str, source: str) -> None:
    if PREDICTION_COUNT:
        PREDICTION_COUNT.labels(level, source).inc()
