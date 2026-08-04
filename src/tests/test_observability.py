"""Tests for observability helpers."""

from unittest.mock import MagicMock

from fastapi import FastAPI

from preprocessing_api.observability import (
    configure_logging,
    configure_tracing,
    generate_latest,
    record_prediction,
)


def test_generate_latest_returns_bytes():
    payload = generate_latest()
    assert isinstance(payload, bytes)


def test_record_prediction_does_not_raise():
    record_prediction("LOW", "rule_fallback")


def test_configure_logging_does_not_raise(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_logging()


def test_configure_tracing_disabled_is_a_noop(monkeypatch):
    monkeypatch.setenv("ENABLE_TRACING", "false")
    configure_tracing(FastAPI())


def test_configure_tracing_enabled_without_endpoint_is_a_noop(monkeypatch):
    monkeypatch.setenv("ENABLE_TRACING", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    configure_tracing(FastAPI())


def test_configure_tracing_enabled_with_endpoint_instruments_app(monkeypatch):
    monkeypatch.setenv("ENABLE_TRACING", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Stub out the exporter/processor so no real background OTLP connection is
    # attempted (configure_tracing's own docstring notes this spams stderr with
    # "connection refused" retries when no collector is running).
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
        lambda *args, **kwargs: MagicMock(),
    )
    monkeypatch.setattr(
        "opentelemetry.sdk.trace.export.BatchSpanProcessor",
        lambda *args, **kwargs: MagicMock(),
    )

    instrumented = {}
    monkeypatch.setattr(
        "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app",
        lambda app: instrumented.setdefault("app", app),
    )

    app = FastAPI()
    configure_tracing(app)

    assert instrumented["app"] is app
