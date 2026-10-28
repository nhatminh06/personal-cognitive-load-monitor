"""Authenticated local focus-session API to Kafka acceptance smoke test."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from confluent_kafka import Consumer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cogniflow_contracts import BehavioralActivityEvent
from cogniflow_data.kafka import KafkaPublisher
from cogniflow_sessions import FocusSessionRepository, publish_pending
from preprocessing_api.main import app
from preprocessing_api.sessions import get_session_repository

ACTIVITY_TOPIC = "cogniflow.behavioral-activity.v1"


def _lifecycle(session_id: str, event_type: str, sequence: int, when: datetime) -> dict:
    return {
        "event_id": str(uuid4()),
        "session_id": session_id,
        "event_time": when.isoformat(),
        "ingested_at": datetime.now(UTC).isoformat(),
        "source": "local_smoke",
        "producer_version": "1.0.0",
        "idempotency_key": f"{session_id}:lifecycle:{sequence}",
        "event_type": event_type,
        "sequence": sequence,
        "session_kind": "programming",
        "privacy_mode": "behavioral",
    }


async def _api_setup(repository: FocusSessionRepository, api_key: str) -> tuple[str, str]:
    async def repository_dependency() -> FocusSessionRepository:
        return repository

    app.dependency_overrides[get_session_repository] = repository_dependency
    session_id = f"smoke-{uuid4()}"
    start = datetime.now(UTC) - timedelta(minutes=10)
    headers = {"x-api-key": api_key}
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
            created = await client.post(
                "/sessions", json=_lifecycle(session_id, "session.started", 1, start),
                headers=headers,
            )
            _expect(created, 201, "create session")
            completed = await client.post(
                f"/sessions/{session_id}/transitions",
                json=_lifecycle(session_id, "session.completed", 2, start + timedelta(minutes=5)),
                headers=headers,
            )
            _expect(completed, 200, "complete session")
            state = await client.get(f"/sessions/{session_id}", headers=headers)
            _expect(state, 200, "read session")
            window = state.json()["completed_windows"][0]
            event_id = str(uuid4())
            activity = {
                "event_id": event_id,
                "session_id": session_id,
                "event_time": window["window_end"],
                "ingested_at": datetime.now(UTC).isoformat(),
                "source": "local_smoke",
                "producer_version": "1.0.0",
                "idempotency_key": f"{session_id}:activity:1",
                "event_type": "behavioral.window",
                **window,
                "feature_cutoff": window["window_end"],
                "active_seconds": 240,
                "idle_seconds": 60,
                "keyboard_event_count": 12,
                "pointer_event_count": 3,
                "application_switch_count": 2,
            }
            accepted = await client.post(
                f"/sessions/{session_id}/activity-windows", json=activity, headers=headers
            )
            _expect(accepted, 201, "submit activity")
            retry = await client.post(
                f"/sessions/{session_id}/activity-windows", json=activity, headers=headers
            )
            _expect(retry, 200, "retry activity")
    finally:
        app.dependency_overrides.clear()
    return session_id, event_id


def _expect(response: httpx.Response, expected: int, operation: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{operation} failed with HTTP {response.status_code}")


def _verify_pending(repository: FocusSessionRepository, session_id: str, event_id: str) -> int:
    timeline = repository.timeline(session_id, _owner(), 100, 0)["items"]
    activity = [item for item in timeline if item.get("event_id") == event_id]
    pending = repository.pending_outbox(100)
    outbox = [row for row in pending if row["event_id"] == event_id]
    if len(activity) != 1 or len(outbox) != 1 or outbox[0]["topic"] != ACTIVITY_TOPIC:
        raise RuntimeError("activity and outbox were not atomically persisted exactly once")
    return len(pending)


def _owner() -> str:
    return hashlib.sha256(os.environ["COGNIFLOW_API_KEY"].encode()).hexdigest()


def _consume(consumer: Consumer, event_id: str, timeout: float = 15) -> tuple[str, int, int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = consumer.poll(0.5)
        if message is None:
            continue
        if message.error():
            raise RuntimeError("Kafka consumer returned an error")
        try:
            event = BehavioralActivityEvent.model_validate_json(message.value())
        except ValueError:
            continue
        if str(event.event_id) == event_id:
            if message.key() != event.session_id.encode():
                raise RuntimeError("Kafka partition key does not match the session ID")
            topic, partition, offset = message.topic(), message.partition(), message.offset()
            if topic is None or partition is None or offset is None:
                raise RuntimeError("Kafka message metadata is incomplete")
            return topic, partition, offset
    raise RuntimeError("matching behavioral event was not consumed before timeout")


def run(database: Path, brokers: str) -> dict[str, object]:
    if database.exists():
        raise RuntimeError("smoke-test database already exists; use a fresh path")
    api_key = os.environ.get("COGNIFLOW_API_KEY") or secrets.token_urlsafe(32)
    os.environ["COGNIFLOW_API_KEY"] = api_key
    os.environ["KAFKA_BOOTSTRAP_SERVERS"] = brokers
    repository = FocusSessionRepository(database)
    session_id, event_id = asyncio.run(_api_setup(repository, api_key))
    pending_before = _verify_pending(repository, session_id, event_id)

    consumer = Consumer({
        "bootstrap.servers": brokers,
        "group.id": f"cogniflow-pr3-smoke-{uuid4()}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([ACTIVITY_TOPIC])
    try:
        published = publish_pending(repository, KafkaPublisher(), limit=25)
        topic, partition, offset = _consume(consumer, event_id)
    finally:
        consumer.close()
    pending_after = repository.pending_outbox(100)
    with sqlite3.connect(database) as connection:
        published_at = connection.execute(
            "SELECT published_at FROM outbox WHERE event_id=?", (event_id,)
        ).fetchone()[0]
    if published != pending_before or pending_after or not published_at:
        raise RuntimeError("acknowledged outbox state is inconsistent")
    return {
        "status": "passed",
        "session_id": session_id,
        "activity_event_id": event_id,
        "topic": topic,
        "partition": partition,
        "offset": offset,
        "published_count": published,
        "pending_before": pending_before,
        "pending_after": 0,
        "idempotent_retry": True,
        "delivery": "at_least_once",
    }


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("preprocessing_api.observability").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument(
        "--brokers", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:29092")
    )
    args = parser.parse_args()
    print(json.dumps(run(args.database, args.brokers), sort_keys=True))


if __name__ == "__main__":
    main()
