"""Small observability helpers for metrics, logging, and tracing."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest  # noqa: F401

LOGGER = logging.getLogger(__name__)

REQUEST_COUNT = Counter(
    "cognitive_load_api_requests_total",
    "Total HTTP requests handled by the API.",
    ["method", "endpoint", "http_status"],
)

REQUEST_LATENCY = Histogram(
    "cognitive_load_api_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "endpoint"],
)

PREDICTION_COUNT = Counter(
    "cognitive_load_predictions_total",
    "Total predictions by level and source.",
    ["level", "source"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        )


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file := os.getenv("LOG_FILE"):
        handlers.append(logging.FileHandler(log_file))
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=handlers, force=True)


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

    REQUEST_COUNT.labels(request.method, endpoint, str(response.status_code)).inc()
    REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)

    return response


class MetricsMiddleware:
    """Record request metrics without Starlette's thread-backed BaseHTTPMiddleware."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status = 500

        async def send_with_metrics(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_metrics)
        finally:
            route = scope.get("route")
            endpoint = route.path if route else scope.get("path", "unknown")
            duration = time.perf_counter() - start
            REQUEST_COUNT.labels(scope["method"], endpoint, str(status)).inc()
            REQUEST_LATENCY.labels(scope["method"], endpoint).observe(duration)
            LOGGER.info(
                "request_complete method=%s endpoint=%s status=%s duration_ms=%.2f",
                scope["method"], endpoint, status, duration * 1000,
            )


def record_prediction(level: str, source: str) -> None:
    PREDICTION_COUNT.labels(level, source).inc()
