"""Versioned event contract and ingestion API tests."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from cogniflow_data.api import event_publisher_dependency
from cogniflow_data.events import SESSION_TOPIC, SessionEvent
from cogniflow_data.kafka import KafkaEventConsumer, KafkaPublisher, PublishError, RecentEventIds
from preprocessing_api.main import app


def event_body(**updates):
    body = {
        "schema_version": "1.0",
        "event_type": "session.snapshot",
        "session_id": "session-001",
        "user_id": "anon_12345",
        "event_time": "2026-10-23T20:00:00Z",
        "source": "module2-test",
        "payload": {
            "focus_minutes": 120,
            "distraction_minutes": 30,
            "tasks_due": 3,
            "hours_to_deadline": 24,
        },
        "provenance": {"producer": "pytest", "producer_version": "1.0"},
    }
    body.update(updates)
    return body


class CapturingPublisher:
    def __init__(self, failure: bool = False):
        self.events = []
        self.failure = failure

    def publish(self, event, topic=SESSION_TOPIC):
        if self.failure:
            raise PublishError("offline")
        self.events.append((event, topic))


def test_event_requires_aware_timestamps_and_valid_payload():
    with pytest.raises(ValidationError, match="timezone"):
        SessionEvent.model_validate(event_body(event_time="2026-10-23T20:00:00"))
    with pytest.raises(ValidationError):
        SessionEvent.model_validate(event_body(payload={
            "focus_minutes": -1,
            "distraction_minutes": 0,
            "tasks_due": 0,
            "hours_to_deadline": 1,
        }))


def test_event_wire_contract_and_session_partition_key():
    event = SessionEvent.model_validate(event_body())
    restored = SessionEvent.model_validate_json(event.wire_bytes())
    assert restored == event
    assert event.kafka_key() == b"session-001"
    assert event.ingested_at.tzinfo == UTC


def test_events_endpoint_acknowledges_only_published_events(client):
    publisher = CapturingPublisher()

    async def dependency():
        return publisher

    app.dependency_overrides[event_publisher_dependency] = dependency
    try:
        response = client.post("/events", json=event_body())
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 202
    assert UUID(response.json()["event_id"])
    assert response.json()["topic"] == SESSION_TOPIC
    assert publisher.events[0][0].ingested_at <= datetime.now(UTC)


def test_events_endpoint_fails_closed_when_kafka_is_unavailable(client):
    async def dependency():
        return CapturingPublisher(failure=True)

    app.dependency_overrides[event_publisher_dependency] = dependency
    try:
        response = client.post("/events", json=event_body())
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {"detail": "Event broker is unavailable"}


def test_events_optional_api_key(client, monkeypatch):
    monkeypatch.setenv("EVENT_API_KEY", "test-secret")

    async def dependency():
        return CapturingPublisher()

    app.dependency_overrides[event_publisher_dependency] = dependency
    try:
        assert client.post("/events", json=event_body()).status_code == 401
        assert client.post(
            "/events", json=event_body(), headers={"x-api-key": "test-secret"}
        ).status_code == 202
    finally:
        app.dependency_overrides.clear()


def test_recent_event_ids_is_bounded_and_detects_duplicates():
    seen = RecentEventIds(capacity=2)
    assert seen.add("a") is True
    assert seen.add("a") is False
    assert seen.add("b") is True
    assert seen.add("c") is True
    assert seen.add("a") is True


def test_kafka_publisher_checks_delivery_acknowledgment():
    class FakeProducer:
        def produce(self, _topic, key, value, on_delivery):
            assert key == b"session-001"
            assert value
            on_delivery("not acknowledged", None)

        def flush(self, _timeout):
            return 0

    with pytest.raises(PublishError, match="acknowledge"):
        KafkaPublisher(FakeProducer()).publish(SessionEvent.model_validate(event_body()))


def test_consumer_deduplicates_and_dead_letters_before_committing():
    class Message:
        def __init__(self, value):
            self._value = value

        def value(self): return self._value
        def key(self): return b"session-001"
        def topic(self): return SESSION_TOPIC
        def partition(self): return 1
        def offset(self): return 2

    class Consumer:
        def __init__(self): self.commits = []
        def commit(self, **kwargs): self.commits.append(kwargs)

    class DeadLetters:
        def __init__(self): self.records = []
        def produce(self, topic, key, value): self.records.append((topic, key, value))
        def flush(self, _timeout): return 0

    consumer, dead_letters, handled = Consumer(), DeadLetters(), []
    worker = KafkaEventConsumer(consumer, dead_letters)
    valid = SessionEvent.model_validate(event_body()).wire_bytes()
    worker.process_message(Message(valid), lambda event, _message: handled.append(event.event_id))
    worker.process_message(Message(valid), lambda event, _message: handled.append(event.event_id))
    worker.process_message(Message(b"not-json"), lambda *_: None)
    assert len(handled) == 1
    assert len(consumer.commits) == 3
    assert dead_letters.records[0][0] == "cogniflow.dead-letter.v1"
