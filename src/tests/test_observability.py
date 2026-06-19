"""Tests for observability helpers."""

from preprocessing_api.observability import configure_logging, generate_latest, record_prediction


def test_generate_latest_returns_bytes():
    payload = generate_latest()
    assert isinstance(payload, bytes)


def test_record_prediction_does_not_raise():
    record_prediction("LOW", "rule_fallback")


def test_configure_logging_does_not_raise(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_logging()
