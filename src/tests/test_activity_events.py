from __future__ import annotations

import json
import asyncio
import threading
import time
import uuid
from datetime import datetime

import pytest
import httpx

from cogniflow_eventing import consumer
from preprocessing_api import activity_events
from preprocessing_api.main import app
from preprocessing_api.security import MAX_REQUEST_BYTES


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


def streamed_request(app, chunks, headers=None):
    async def send():
        async def stream():
            for chunk in chunks:
                yield chunk

        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/", content=stream(), headers=headers)

    return asyncio.run(send())


def test_publisher_rejects_external_destination(monkeypatch):
    monkeypatch.setenv("INFERENCE_ACTIVITY_ENABLED", "true")
    monkeypatch.setenv("INFERENCE_ACTIVITY_DESTINATION", "https://attacker.example/events")
    assert asyncio.run(activity_events.publish_activity_event(event())) is False


def test_publisher_is_bounded_and_reports_success(monkeypatch):
    called = []
    monkeypatch.setenv("INFERENCE_ACTIVITY_ENABLED", "true")
    monkeypatch.setenv("INFERENCE_ACTIVITY_DESTINATION", "http://127.0.0.1:9999/events")
    monkeypatch.setattr(activity_events, "_post", lambda payload, destination, timeout: called.append(payload))
    assert asyncio.run(activity_events.publish_activity_event(event())) is True
    assert len(called[0]) < activity_events.MAX_EVENT_BYTES


def test_publisher_concurrency_is_bounded_and_cancellation_does_not_release_early(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def block(*_args):
        started.set()
        release.wait(timeout=2)

    monkeypatch.setenv("INFERENCE_ACTIVITY_ENABLED", "true")
    monkeypatch.setenv("INFERENCE_ACTIVITY_DESTINATION", "http://127.0.0.1:9999/events")
    monkeypatch.setattr(activity_events, "_post", block)

    async def exercise():
        first = asyncio.create_task(activity_events.publish_activity_event(event()))
        while not started.is_set():
            await asyncio.sleep(0.001)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        remaining = [asyncio.create_task(activity_events.publish_activity_event(event())) for _ in range(4)]
        await asyncio.sleep(0.01)
        assert sum(task.done() for task in remaining) == 1
        assert next(task for task in remaining if task.done()).result() is False
        release.set()
        assert all(await asyncio.gather(*(task for task in remaining if not task.done())))

    asyncio.run(exercise())


def test_publisher_timeout_returns_without_unbounded_background_work(monkeypatch):
    release = threading.Event()
    monkeypatch.setenv("INFERENCE_ACTIVITY_ENABLED", "true")
    monkeypatch.setenv("INFERENCE_ACTIVITY_DESTINATION", "http://127.0.0.1:9999/events")
    monkeypatch.setenv("INFERENCE_ACTIVITY_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setattr(activity_events, "_post", lambda *_args: release.wait(timeout=1))
    started = time.monotonic()
    assert asyncio.run(activity_events.publish_activity_event(event())) is False
    assert time.monotonic() - started < 0.5
    release.set()


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


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [
        ({}, 413),
        ({"content-length": "invalid"}, 400),
    ],
)
def test_security_rejections_are_captured_as_sanitized_activity(
    monkeypatch, headers, expected_status
):
    captured = []

    async def capture(value):
        captured.append(value)
        return True

    monkeypatch.setenv("INFERENCE_MODE", "demo_rule")
    monkeypatch.setattr(activity_events, "publish_activity_event", capture)
    content = b"sensitive-marker" + (b"x" * MAX_REQUEST_BYTES if expected_status == 413 else b"")
    response = request(app, "POST", "/predict", headers=headers, content=content)
    assert response.status_code == expected_status
    assert response.headers["x-correlation-id"] == captured[0]["data"]["correlation_id"]
    assert captured[0]["data"]["http_status"] == response.status_code
    assert "sensitive-marker" not in json.dumps(captured[0])


@pytest.mark.parametrize(
    ("headers", "payload", "expected_status"),
    [
        ({}, {"focus_minutes": 45, "distraction_minutes": 5, "tasks_due": 2,
              "hours_to_deadline": 24}, 401),
        ({"x-api-key": "test-api-key"}, {"focus_minutes": -1}, 422),
    ],
)
def test_authentication_and_validation_failures_publish_activity(
    monkeypatch, headers, payload, expected_status
):
    captured = []

    async def capture(value):
        captured.append(value)
        return True

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("COGNIFLOW_API_KEY", "test-api-key")
    monkeypatch.setenv("INFERENCE_MODE", "demo_rule")
    monkeypatch.setattr(activity_events, "publish_activity_event", capture)
    response = request(app, "POST", "/predict", headers=headers, json=payload)
    assert response.status_code == expected_status
    assert captured[0]["data"]["http_status"] == expected_status
    assert captured[0]["data"]["failure_category"] in {"authentication", "validation"}


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


@pytest.mark.parametrize("field", ["id", "correlation_id"])
@pytest.mark.parametrize("invalid", [1, True, [], {}, None, "not-a-uuid"])
def test_consumer_rejects_non_string_and_invalid_uuid_ids(tmp_path, monkeypatch, field, invalid):
    monkeypatch.setenv("EVENT_STORE_PATH", str(tmp_path / "events.sqlite3"))
    payload = event()
    if field == "id":
        payload["id"] = invalid
    else:
        payload["data"]["correlation_id"] = invalid
    response = request(
        consumer.app,
        "POST",
        "/",
        content=json.dumps(payload),
        headers={"content-type": "application/cloudevents+json"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid activity event"}


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


@pytest.mark.parametrize("headers", [None, {"content-length": "1"}])
def test_consumer_rejects_oversized_stream_without_trusting_content_length(
    tmp_path, monkeypatch, headers
):
    monkeypatch.setenv("EVENT_STORE_PATH", str(tmp_path / "events.sqlite3"))
    chunks = [b"x" * 2048, b"y" * 2048, b"z"]
    response = streamed_request(
        consumer.app,
        chunks,
        {"content-type": "application/cloudevents+json", **(headers or {})},
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
