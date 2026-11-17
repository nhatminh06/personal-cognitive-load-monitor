"""Component rehearsal: real API events and durable stores, no Kubernetes transport."""

import asyncio
import json

import httpx

from cogniflow_anomaly import detector, sink
from cogniflow_eventing import consumer
from preprocessing_api import activity_events


def test_authenticated_inference_to_durable_alert(client, monkeypatch, tmp_path):
    monkeypatch.setenv("COGNIFLOW_API_KEY", "component-test-key")
    monkeypatch.setenv("INFERENCE_MODE", "demo_rule")
    for variable, filename in (
        ("EVENT_STORE_PATH", "events.sqlite3"),
        ("ANOMALY_STORE_PATH", "detector.sqlite3"),
        ("ALERT_STORE_PATH", "alerts.sqlite3"),
    ):
        monkeypatch.setenv(variable, str(tmp_path / filename))
    monkeypatch.setenv("ANOMALY_ALERT_DESTINATION", "http://127.0.0.1:9999/")
    monkeypatch.setenv("INFERENCE_MEAN_LATENCY_MS_THRESHOLD", "3600000")
    captured = []

    async def capture(event):
        captured.append(event)
        return True

    monkeypatch.setattr(activity_events, "publish_activity_event", capture)
    payload = {"focus_minutes": 45, "distraction_minutes": 5, "tasks_due": 2,
               "hours_to_deadline": 24}
    for _ in range(2):
        response = client.post("/predict", json=payload,
                               headers={"x-api-key": "component-test-key"})
        assert response.status_code == 200
        assert response.json()["inference_source"] == "demo_rule"
    for _ in range(2):
        assert client.post("/predict", json=payload).status_code == 401
    assert len(captured) == 4

    def deliver(app, event):
        async def send():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://test") as session:
                return await session.post("/", json=event,
                                          headers={"content-type": "application/cloudevents+json"})
        return asyncio.run(send())

    alerts = []
    for event in captured:
        consumer.validate_event(event)
        serialized = json.dumps(event)
        assert all(value not in serialized for value in
                   ("component-test-key", "focus_minutes", "distraction_minutes"))
        assert deliver(consumer.app, event).status_code == 204
        outcome, generated = detector.process_event(event)
        assert outcome == "processed"
        alerts.extend(generated)
    assert [alert["data"]["rule_id"] for alert in alerts] == ["inference_error_ratio"]

    # Each operation reopens SQLite; replays must survive closed connections.
    for event in captured:
        assert deliver(consumer.app, event).status_code == 204
        assert detector.process_event(event)[0] == "duplicate"
    with consumer._connection() as connection:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 4

    def unavailable(*args, **kwargs):
        raise OSError("simulated sink outage")

    monkeypatch.setattr(detector.urllib.request.OpenerDirector, "open", unavailable)
    assert detector.flush_outbox() is False
    with detector._connect() as connection:
        assert connection.execute("SELECT attempts FROM outbox").fetchone()[0] == 1

    class Accepted:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def recovered(_opener, request, **kwargs):
        alert = json.loads(request.data)
        assert deliver(sink.app, alert).status_code == 204
        assert deliver(sink.app, alert).status_code == 204
        return Accepted()

    monkeypatch.setattr(detector.urllib.request.OpenerDirector, "open", recovered)
    assert detector.flush_outbox() is True
    with sink._connect() as connection:
        assert connection.execute("SELECT count(*) FROM alerts").fetchone()[0] == 1
    with detector._connect() as connection:
        assert connection.execute("SELECT published_at FROM outbox").fetchone()[0]
