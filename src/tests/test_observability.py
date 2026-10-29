"""Tests for observability helpers."""

from unittest.mock import MagicMock
from pathlib import Path

from fastapi import FastAPI
import yaml

from preprocessing_api.observability import (
    JsonFormatter,
    configure_logging,
    configure_tracing,
    generate_latest,
    record_prediction,
)


def test_json_formatter_emits_structured_safe_fields():
    import json
    import logging

    payload = json.loads(JsonFormatter().format(logging.LogRecord(
        "api", logging.INFO, __file__, 1, "prediction complete", (), None
    )))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "api"
    assert payload["message"] == "prediction complete"
    assert "timestamp" in payload


def test_json_formatter_adds_only_valid_trace_correlation(monkeypatch):
    import json
    import logging

    context = MagicMock(is_valid=True, trace_id=0x12, span_id=0x34)
    span = MagicMock()
    span.get_span_context.return_value = context
    monkeypatch.setattr("opentelemetry.trace.get_current_span", lambda: span)

    payload = json.loads(JsonFormatter().format(logging.LogRecord(
        "api", logging.INFO, __file__, 1, "request complete", (), None
    )))
    assert payload["trace_id"] == "00000000000000000000000000000012"
    assert payload["span_id"] == "0000000000000034"
    assert set(payload) == {"timestamp", "level", "logger", "message", "trace_id", "span_id"}


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
        lambda app, **kwargs: instrumented.update(app=app, provider=kwargs["tracer_provider"]),
    )
    monkeypatch.setattr(
        "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor.instrument",
        lambda self, **kwargs: instrumented.update(httpx_provider=kwargs["tracer_provider"]),
    )

    app = FastAPI()
    configure_tracing(app)

    assert instrumented["app"] is app
    assert instrumented["provider"] is instrumented["httpx_provider"]
    assert instrumented["provider"].resource.attributes["service.name"] == "cognitive-load-api"


def test_promtail_labels_api_and_kserve_logs_separately():
    config = yaml.safe_load(Path("infra/observability/promtail/config.yml").read_text())
    labels = [item["static_configs"][0]["labels"] for item in config["scrape_configs"]]

    assert labels == [
        {
            "job": "cognitive-load-api",
            "service_name": "cognitive-load-api",
            "__path__": "/var/log/cogniflow/api.log",
        },
        {
            "job": "cognitive-load-kserve",
            "service_name": "cognitive-load-kserve",
            "__path__": "/var/log/cogniflow/kserve.log",
        },
    ]
