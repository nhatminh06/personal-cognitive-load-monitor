"""Behavioral ingestion, outbox, replay, Bronze, and online parity tests."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import uuid4

import httpx
import pytest

from cogniflow_contracts import BehavioralActivityEvent, SessionLifecycleEvent
from cogniflow_data.behavioral import behavioral_features, replay_behavioral_features
from cogniflow_data.bronze import BronzeRecord, BronzeStore, KafkaPosition
from cogniflow_data.kafka import PublishError
from cogniflow_data.online import RedisFeatureStore
from cogniflow_sessions import FocusSessionRepository, publish_pending
from preprocessing_api.main import app
from preprocessing_api.sessions import get_session_repository

START = datetime.now(UTC) - timedelta(hours=1)
OWNER = hashlib.sha256(b"session-secret").hexdigest()


def lifecycle(session_id: str, kind: str, sequence: int, when: datetime) -> SessionLifecycleEvent:
    return SessionLifecycleEvent(
        event_id=uuid4(), session_id=session_id, event_time=when,
        ingested_at=when + timedelta(seconds=1), source="local_api", producer_version="1.0.0",
        idempotency_key=f"{session_id}:{sequence}", event_type=f"session.{kind}",
        sequence=sequence, session_kind="programming", privacy_mode="behavioral",
    )


def activity(session_id: str, window: dict, **changes) -> BehavioralActivityEvent:
    payload = {
        "event_id": uuid4(), "session_id": session_id,
        "event_time": window["window_end"], "ingested_at": START + timedelta(minutes=10),
        "source": "local_agent", "producer_version": "1.0.0",
        "idempotency_key": f"{session_id}:activity:1", "window_id": window["window_id"],
        "window_start": window["window_start"], "window_end": window["window_end"],
        "feature_cutoff": window["window_end"], "active_seconds": 240, "idle_seconds": 60,
        "keyboard_event_count": 120, "pointer_event_count": 30,
        "application_switch_count": 2,
    }
    payload.update(changes)
    return BehavioralActivityEvent.model_validate(payload)


def prepared_repository(tmp_path, session_id="behavioral-1"):
    repository = FocusSessionRepository(tmp_path / "sessions.sqlite3")
    repository.create(lifecycle(session_id, "started", 1, START), OWNER)
    repository.transition(
        lifecycle(session_id, "paused", 2, START + timedelta(minutes=6)), OWNER
    )
    window = repository.session(session_id, OWNER)["completed_windows"][0]
    return repository, window


def request(path: str, payload: dict, repository: FocusSessionRepository, monkeypatch):
    monkeypatch.setenv("COGNIFLOW_API_KEY", "session-secret")

    async def dependency():
        return repository

    async def send():
        app.dependency_overrides[get_session_repository] = dependency
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post(path, json=payload, headers={"x-api-key": "session-secret"})
        finally:
            app.dependency_overrides.clear()

    return asyncio.run(send())


def test_activity_api_accepts_completed_window_and_is_idempotent(tmp_path, monkeypatch):
    repository, window = prepared_repository(tmp_path)
    event = activity("behavioral-1", window)
    first = request(
        "/sessions/behavioral-1/activity-windows", event.model_dump(mode="json"),
        repository, monkeypatch,
    )
    second = request(
        "/sessions/behavioral-1/activity-windows", event.model_dump(mode="json"),
        repository, monkeypatch,
    )
    assert first.status_code == 201
    assert second.status_code == 200
    timeline = repository.timeline("behavioral-1", OWNER, 100, 0)
    assert sum(item.get("event_type") == "behavioral.window" for item in timeline["items"]) == 1


def test_activity_rejects_incomplete_pause_window_conflicts_and_private_fields(
    tmp_path, monkeypatch
):
    repository, window = prepared_repository(tmp_path)
    event = activity("behavioral-1", window)
    assert request(
        "/sessions/behavioral-1/activity-windows",
        {**event.model_dump(mode="json"), "window_title": "private.py"},
        repository, monkeypatch,
    ).status_code == 422
    wrong = event.model_copy(update={"window_id": uuid4(), "idempotency_key": "wrong-window"})
    assert request(
        "/sessions/behavioral-1/activity-windows", wrong.model_dump(mode="json"),
        repository, monkeypatch,
    ).status_code == 409
    repository.add_activity(event, OWNER)
    conflicting = event.model_copy(update={
        "event_id": uuid4(), "idempotency_key": "conflict", "active_seconds": 200,
    })
    with pytest.raises(ValueError, match="already has"):
        repository.add_activity(conflicting, OWNER)
    with pytest.raises(ValueError, match="not found"):
        repository.add_activity(event.model_copy(update={
            "session_id": "other", "event_id": uuid4(), "idempotency_key": "other:activity",
        }), OWNER)


def test_outbox_ack_failure_crash_recovery_and_partition_key(tmp_path):
    repository, window = prepared_repository(tmp_path)
    event = activity("behavioral-1", window)
    repository.add_activity(event, OWNER)

    class Publisher:
        def __init__(self, failure=None):
            self.failure, self.records = failure, []

        def publish_bytes(self, value, key, topic):
            if self.failure:
                raise self.failure
            self.records.append((value, key, topic))

    failed = Publisher(PublishError("offline"))
    assert publish_pending(repository, failed, limit=10) == 0
    assert repository.pending_outbox(10)[0]["attempts"] == 1
    with pytest.raises(RuntimeError, match="crash"):
        publish_pending(repository, Publisher(RuntimeError("crash")), limit=10)
    assert all(row["published_at"] is None for row in _outbox_rows(repository))

    recovered = Publisher()
    assert publish_pending(repository, recovered, limit=10) == 3
    assert recovered.records[-1][1] == b"behavioral-1"
    assert recovered.records[-1][2] == "cogniflow.behavioral-activity.v1"
    assert repository.pending_outbox(10) == []


def _outbox_rows(repository):
    with repository._connection() as connection:
        return connection.execute("SELECT * FROM outbox ORDER BY rowid").fetchall()


def test_online_offline_and_bronze_behavioral_parity(tmp_path):
    repository, window = prepared_repository(tmp_path)
    event = activity("behavioral-1", window)
    expected = behavioral_features(event)
    assert replay_behavioral_features([event, event]) == [expected]
    with pytest.raises(ValueError, match="conflicting duplicate"):
        replay_behavioral_features([event, event.model_copy(update={"active_seconds": 1})])

    class RedisClient:
        def get(self, key):
            assert key == "cogniflow:behavioral-features:v1:behavioral-1"
            return expected.model_dump_json().encode()

    online = RedisFeatureStore.__new__(RedisFeatureStore)
    online.client, online._redis_error = RedisClient(), RuntimeError
    assert online.get_behavioral("behavioral-1") == expected

    class ClientError(Exception):
        def __init__(self):
            self.response = {"ResponseMetadata": {"HTTPStatusCode": 404}}

    class S3:
        class exceptions:
            pass
        exceptions.ClientError = ClientError

        def __init__(self):
            self.objects = {}
        def head_object(self, Bucket, Key):
            if Key not in self.objects:
                raise ClientError()
            return {"Metadata": self.objects[Key][1]}
        def put_object(self, Bucket, Key, Body, ContentType, Metadata):
            self.objects[Key] = (Body, Metadata)
        def get_object(self, Bucket, Key):
            return {"Body": BytesIO(self.objects[Key][0])}

    store = BronzeStore(S3(), "bronze")
    record = BronzeRecord(event, KafkaPosition("cogniflow.behavioral-activity.v1", 0, 4))
    key = store.write_batch([record])
    assert key.startswith("behavioral_activity/schema_version=1.0/")
    assert store.read_batch(key) == [record]
