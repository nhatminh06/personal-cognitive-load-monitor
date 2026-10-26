from __future__ import annotations

import json
import asyncio
import uuid
from datetime import datetime

import pytest
import httpx

from cogniflow_eventing import consumer
from preprocessing_api import activity_events
from preprocessing_api.main import app


def event(**overrides):
    value = activity_events.build_activity_event(
        correlation_id=str(uuid.uuid4()), status=200, backend="demo_rule", latency_ms=12.5
    )
    value.update(overrides)
    return value


def test_event_contract_is_unique_utc_and_sanitized(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret-that-must-not-appear")
    first = event()
    second = event()
    assert first["id"] != second["id"]
    assert datetime.fromisoformat(first["time"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    serialized = json.dumps(first)
    for prohibited in ("secret-that-must-not-appear", "focus_minutes", "authorization"):
        assert prohibited not in serialized.lower()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"backend": "unknown"}, "backend"),
        ({"status": 99}, "status"),
        ({"latency_ms": float("nan")}, "latency"),
        ({"correlation_id": "not-a-uuid"}, "UUID"),
    ],
)
def test_event_contract_rejects_invalid_values(kwargs, message):
    values = {"correlation_id": str(uuid.uuid4()), "status": 200, "backend": "demo_rule", "latency_ms": 1}
    values.update(kwargs)
    with pytest.raises(ValueError, match=message):
        activity_events.build_activity_event(**values)


def request(app, method, path, **kwargs):
    async def send():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_publisher_rejects_external_destination(monkeypatch):
    monkeypatch.setenv("INFERENCE_ACTIVITY_ENABLED", "true")
    monkeypatch.setenv("INFERENCE_ACTIVITY_DESTINATION", "https://attacker.example/events")
    assert asyncio.run(activity_events.publish_activity_event(event())) is False


def test_publisher_is_bounded_and_reports_success(monkeypatch):
    called = []

    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setenv("INFERENCE_ACTIVITY_ENABLED", "true")
    monkeypatch.setenv("INFERENCE_ACTIVITY_DESTINATION", "http://127.0.0.1:9999/events")
    monkeypatch.setattr(activity_events, "_post", lambda payload, destination, timeout: called.append(payload))
    monkeypatch.setattr(activity_events.asyncio, "to_thread", run_inline)
    assert asyncio.run(activity_events.publish_activity_event(event())) is True
    assert len(called[0]) < activity_events.MAX_EVENT_BYTES


def test_prediction_unchanged_when_publication_fails(monkeypatch):
    async def fail(_event):
        return False

    monkeypatch.setenv("INFERENCE_MODE", "demo_rule")
    monkeypatch.setattr(activity_events, "publish_activity_event", fail)
    response = request(
        app,
        "POST",
        "/predict",
        headers={"x-api-key": "test-api-key"},
        json={"focus_minutes": 45, "distraction_minutes": 5, "tasks_due": 2, "hours_to_deadline": 24},
    )
    assert response.status_code == 200
    assert response.headers["x-correlation-id"]
    assert response.json()["inference_source"] == "demo_rule"


def test_consumer_persists_once_and_survives_restart(tmp_path, monkeypatch):
    store = tmp_path / "events.sqlite3"
    monkeypatch.setenv("EVENT_STORE_PATH", str(store))
    payload = event()
    kwargs = {"json": payload, "headers": {"content-type": "application/cloudevents+json"}}
    assert request(consumer.app, "POST", "/", **kwargs).status_code == 204
    assert request(consumer.app, "POST", "/", **kwargs).status_code == 204
    with consumer._connection() as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    assert request(consumer.app, "GET", "/ready").status_code == 200


def test_consumer_accepts_knative_binary_delivery(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_STORE_PATH", str(tmp_path / "events.sqlite3"))
    payload = event()
    data = payload.pop("data")
    headers = {f"ce-{key}": str(value) for key, value in payload.items() if key != "datacontenttype"}
    response = request(consumer.app, "POST", "/", json=data, headers=headers)
    assert response.status_code == 204


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(specversion="0.3"),
        lambda value: value.update(type="org.example.unsupported"),
        lambda value: value["data"].update(inference_backend="other"),
        lambda value: value["data"].update(latency_ms=float("inf")),
        lambda value: value["data"].update(raw_features=[1, 2, 3]),
        lambda value: value["data"].update(outcome="failure"),
    ],
)
def test_consumer_rejects_invalid_events(tmp_path, monkeypatch, mutation):
    monkeypatch.setenv("EVENT_STORE_PATH", str(tmp_path / "events.sqlite3"))
    payload = event()
    mutation(payload)
    response = request(
        consumer.app, "POST", "/", content=json.dumps(payload),
        headers={"content-type": "application/cloudevents+json"}
    )
    assert response.status_code == 400
    assert "raw_features" not in response.text


def test_consumer_failure_is_retryable_and_size_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_STORE_PATH", str(tmp_path / "events.sqlite3"))
    monkeypatch.setenv("CONSUMER_FORCE_FAILURE", "true")
    assert request(consumer.app, "POST", "/", json=event()).status_code == 503
    monkeypatch.delenv("CONSUMER_FORCE_FAILURE")
    response = request(
        consumer.app, "POST", "/", content=b"x" * (activity_events.MAX_EVENT_BYTES + 1),
        headers={"content-type": "application/json"}
    )
    assert response.status_code == 413


def test_knative_manifests_have_bounded_delivery_and_private_services():
    trigger = open("deploy/knative/trigger.yaml", encoding="utf-8").read()
    resources = open("deploy/knative/consumer.yaml", encoding="utf-8").read()
    assert "retry: 3" in trigger
    assert "backoffPolicy: exponential" in trigger
    assert "deadLetterSink:" in trigger
    assert "type: ClusterIP" in resources
    assert "readOnlyRootFilesystem: true" in resources
    assert "imagePullPolicy: Never" in resources
