from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from cogniflow_anomaly import detector, sink


def activity(index: int, *, when: datetime | None = None, failed: bool = False, latency: float = 10) -> dict:
    timestamp = when or datetime(2026, 10, 27, tzinfo=UTC) + timedelta(seconds=index)
    status = 503 if failed else 200
    return {
        "specversion": "1.0", "id": str(uuid.UUID(int=index + 1)),
        "source": "urn:cogniflow:preprocessing-api", "type": "org.cogniflow.inference.activity.v1",
        "time": timestamp.isoformat().replace("+00:00", "Z"), "datacontenttype": "application/json",
        "data": {"schema_version": "1.0", "correlation_id": str(uuid.UUID(int=10_000 + index)),
                 "outcome": "failure" if failed else "success", "http_status": status,
                 "inference_backend": "demo_rule", "latency_ms": latency,
                 "failure_category": "backend_unavailable" if failed else "none"},
    }


def request(app, payload):
    async def send():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/", content=json.dumps(payload), headers={"content-type": "application/cloudevents+json"})
    return asyncio.run(send())


@pytest.fixture(autouse=True)
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("ANOMALY_STORE_PATH", str(tmp_path / "detector.sqlite3"))
    monkeypatch.setenv("ALERT_STORE_PATH", str(tmp_path / "alerts.sqlite3"))
    monkeypatch.setenv("ANOMALY_ALERT_DESTINATION", "http://127.0.0.1:9999/")


def test_normal_and_boundary_events_do_not_alert():
    for index in range(5):
        outcome, alerts = detector.process_event(activity(index, failed=index == 0, latency=499.999))
        assert outcome == "processed"
        assert alerts == []


def test_error_burst_generates_one_alert_and_replay_is_idempotent():
    alerts = []
    for index in range(4):
        _, alerts = detector.process_event(activity(index, failed=index >= 2))
    assert [item["data"]["rule_id"] for item in alerts] == ["inference_error_ratio"]
    assert alerts[0]["data"]["observed_metric"] == 0.5
    assert detector.process_event(activity(3, failed=True))[0] == "duplicate"
    with detector._connect() as connection:
        assert connection.execute("SELECT count(*) FROM alerts").fetchone()[0] == 1


def test_latency_spike_and_rate_spike_are_deterministic():
    produced = []
    for index in range(6):
        _, alerts = detector.process_event(activity(index, latency=500))
        produced.extend(alerts)
    assert [item["data"]["rule_id"] for item in produced] == ["inference_mean_latency_ms", "inference_request_count"]
    assert produced[1]["data"]["observed_metric"] == 6


def test_cooldown_suppresses_alert_storm():
    for index in range(4):
        detector.process_event(activity(index, failed=True))
    _, alerts = detector.process_event(activity(4, failed=True))
    assert alerts == []


def test_out_of_order_within_bound_and_late_policy():
    base = datetime(2026, 10, 27, tzinfo=UTC)
    detector.process_event(activity(0, when=base + timedelta(seconds=20)))
    assert detector.process_event(activity(1, when=base + timedelta(seconds=15)))[0] == "processed"
    assert detector.process_event(activity(2, when=base))[0] == "late"
    with detector._connect() as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 2


def test_restart_reopens_state_and_outbox_failure_recovers(monkeypatch):
    for index in range(4):
        detector.process_event(activity(index, failed=True))
    monkeypatch.setattr(detector.urllib.request.OpenerDirector, "open", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))
    assert detector.flush_outbox() is False
    with detector._connect() as connection:
        assert connection.execute("SELECT attempts FROM outbox").fetchone()[0] == 1

    class Accepted:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *_args): return None

    monkeypatch.setattr(detector.urllib.request.OpenerDirector, "open", lambda *_args, **_kwargs: Accepted())
    assert detector.flush_outbox() is True
    with detector._connect() as connection:
        assert connection.execute("SELECT published_at FROM outbox").fetchone()[0]


def test_detector_rejects_unsupported_and_oversized_events(monkeypatch):
    monkeypatch.setattr(detector, "flush_outbox", lambda: True)
    wrong = activity(0)
    wrong["type"] = "org.example.wrong"
    response = request(detector.app, wrong)
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid activity event"}

    async def oversized():
        async def stream():
            yield b"x" * 4096
            yield b"x"
        transport = httpx.ASGITransport(app=detector.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/", content=stream())
    assert asyncio.run(oversized()).status_code == 413


def test_sink_persists_alert_once_without_sensitive_fields():
    alert = None
    for index in range(4):
        _, alerts = detector.process_event(activity(index, failed=True))
        if alerts:
            alert = alerts[0]
    assert alert is not None
    serialized = json.dumps(alert)
    assert all(value not in serialized for value in ("api_key", "focus_minutes", "correlation_id"))
    assert request(sink.app, alert).status_code == 204
    assert request(sink.app, alert).status_code == 204
    with sink._connect() as connection:
        assert connection.execute("SELECT count(*) FROM alerts").fetchone()[0] == 1


def test_sink_rejects_tampered_alert():
    invalid = {"specversion": "1.0", "type": detector.ALERT_TYPE, "source": detector.ALERT_SOURCE, "data": {}}
    response = request(sink.app, invalid)
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid anomaly alert"}


def test_invalid_rule_configuration_fails_readiness_closed(monkeypatch):
    monkeypatch.setenv("INFERENCE_ERROR_RATIO_WINDOW_SECONDS", "0")

    async def get_ready():
        transport = httpx.ASGITransport(app=detector.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/ready")

    assert asyncio.run(get_ready()).status_code == 503


def test_event_state_record_count_is_bounded(monkeypatch):
    monkeypatch.setattr(detector, "MAX_STATE_EVENTS", 6)
    for index in range(7):
        detector.process_event(activity(index))
    with detector._connect() as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 6


class Accepted:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def wait_until(predicate, timeout=2):
    async def wait():
        deadline = asyncio.get_running_loop().time() + timeout
        while not predicate():
            assert asyncio.get_running_loop().time() < deadline
            await asyncio.sleep(0.01)

    return wait()


def pending_count():
    with detector._connect() as connection:
        return connection.execute("SELECT count(*) FROM outbox WHERE published_at IS NULL").fetchone()[0]


def make_alert():
    alert = None
    for index in range(4):
        _, alerts = detector.process_event(activity(index, failed=True))
        alert = alerts[0] if alerts else alert
    assert alert is not None
    return alert


def test_background_worker_recovers_without_new_event(monkeypatch):
    available = False

    def publish(*_args, **_kwargs):
        if not available:
            raise OSError("sink unavailable")
        return Accepted()

    monkeypatch.setattr(detector.urllib.request.OpenerDirector, "open", publish)

    async def exercise():
        nonlocal available
        async with detector.lifespan(detector.app):
            make_alert()
            await wait_until(lambda: pending_count() == 1)
            available = True
            await wait_until(lambda: pending_count() == 0)

    asyncio.run(exercise())


def test_outbox_larger_than_batch_drains_and_partial_failure_retries(monkeypatch):
    rule = detector.DEFAULT_RULES[0]
    monkeypatch.setattr(detector, "DEFAULT_RULES", (detector.Rule(**{**rule.__dict__, "cooldown_seconds": 0}),))
    monkeypatch.setattr(detector, "OUTBOX_BATCH_SIZE", 2)
    for index in range(7):
        detector.process_event(activity(index, failed=True))
    assert pending_count() == 4
    calls = []

    def publish(_opener, request, **_kwargs):
        event_id = json.loads(request.data)["id"]
        calls.append(event_id)
        if len(calls) == 2:
            raise OSError("partial failure")
        return Accepted()

    monkeypatch.setattr(detector.urllib.request.OpenerDirector, "open", publish)
    assert detector.flush_outbox() is False
    assert detector.flush_outbox() is False
    assert detector.flush_outbox() is True
    assert calls[0] not in calls[2:]
    assert len(calls) == 5


def test_restart_drains_pending_outbox_without_delivery(monkeypatch):
    monkeypatch.setattr(
        detector.urllib.request.OpenerDirector,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )

    async def first_run():
        async with detector.lifespan(detector.app):
            make_alert()
            await wait_until(lambda: pending_count() == 1)

    asyncio.run(first_run())
    monkeypatch.setattr(detector.urllib.request.OpenerDirector, "open", lambda *_a, **_k: Accepted())

    async def restarted():
        async with detector.lifespan(detector.app):
            await wait_until(lambda: pending_count() == 0)

    asyncio.run(restarted())


def test_concurrent_deliveries_are_bounded_and_ack_persisted_events(monkeypatch):
    active = 0
    maximum = 0
    original = detector.process_event

    def tracked(event):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        try:
            return original(event)
        finally:
            active -= 1

    monkeypatch.setattr(detector, "process_event", tracked)

    async def exercise():
        async with detector.lifespan(detector.app):
            transport = httpx.ASGITransport(app=detector.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                responses = await asyncio.gather(*(
                    client.post("/", content=json.dumps(activity(index)), headers={"content-type": "application/cloudevents+json"})
                    for index in range(20)
                ))
        assert {response.status_code for response in responses} == {204}

    asyncio.run(exercise())
    assert maximum <= detector.MAX_CONCURRENT_REQUESTS
    with detector._connect() as connection:
        assert connection.execute("SELECT count(*) FROM deliveries").fetchone()[0] == 20


def test_connections_close_after_success_and_rollback(monkeypatch):
    original = sqlite3.connect
    connections = []

    class TrackingConnection(sqlite3.Connection):
        def close(self):
            super().close()
            connections.append(self)

    monkeypatch.setattr(
        detector.sqlite3,
        "connect",
        lambda *args, **kwargs: original(*args, **kwargs, factory=TrackingConnection),
    )
    with detector._connect() as connection:
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError):
        with detector._connect():
            raise RuntimeError("rollback")
    assert len(connections) == 2
    assert all_raises_closed(connections)


def test_cancellation_waits_for_bounded_worker(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def blocked(_event):
        started.set()
        release.wait()

    monkeypatch.setattr(detector, "process_event", blocked)

    async def exercise():
        task = asyncio.create_task(detector._process_event(activity(0)))
        await asyncio.to_thread(started.wait)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())


def all_raises_closed(connections):
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
    return True


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("data", "triggering_event_id"), []),
        (("data", "backend"), {}),
        (("data", "observed_metric"), "0.5"),
        (("data", "sample_count"), True),
        (("data", "window_start"), 123),
        (("id",), []),
    ],
)
def test_sink_rejects_malformed_field_types(path, value):
    alert = make_alert()
    target = alert
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert request(sink.app, alert).status_code == 400


def test_replay_stays_duplicate_after_window_eviction():
    first = activity(0)
    assert detector.process_event(first)[0] == "processed"
    detector.process_event(activity(1, when=datetime(2026, 10, 27, tzinfo=UTC) + timedelta(hours=2)))
    with detector._connect() as connection:
        assert connection.execute("SELECT count(*) FROM events WHERE id=?", (first["id"],)).fetchone()[0] == 0
    assert detector.process_event(first)[0] == "duplicate"


def test_dedup_storage_and_retry_rate_are_bounded(monkeypatch):
    monkeypatch.setattr(detector, "MAX_DEDUP_EVENTS", 5)
    for index in range(7):
        detector.process_event(activity(index))
    with detector._connect() as connection:
        assert connection.execute("SELECT count(*) FROM deliveries").fetchone()[0] == 5
        connection.execute("DELETE FROM outbox")
        connection.execute("DELETE FROM alerts")

    for index in range(100, 104):
        detector.process_event(activity(index, failed=True))
    assert pending_count() == 1
    monkeypatch.setattr(
        detector.urllib.request.OpenerDirector,
        "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")),
    )

    async def exercise():
        stop, wake = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(detector._outbox_worker(stop, wake))
        await asyncio.sleep(0.35)
        stop.set()
        wake.set()
        await task

    asyncio.run(exercise())
    with detector._connect() as connection:
        attempts = connection.execute("SELECT max(attempts) FROM outbox").fetchone()[0]
    assert attempts <= 2


def test_durable_backlog_limit_is_explicit_overload(monkeypatch):
    monkeypatch.setattr(detector, "MAX_OUTBOX_BACKLOG", 1)
    make_alert()
    response = request(detector.app, activity(99))
    assert response.status_code == 503
    assert response.json() == {"detail": "durable alert backlog full"}
