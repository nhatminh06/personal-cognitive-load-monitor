"""Live Kafka to Flink to Redis behavioral acceptance harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import redis
from confluent_kafka import Consumer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cogniflow_contracts import BehavioralActivityEvent
from cogniflow_data.behavioral import BehavioralFeatureRecord, behavioral_features
from cogniflow_data.kafka import KafkaPublisher
from cogniflow_sessions import FocusSessionRepository, publish_pending
from preprocessing_api.main import app
from preprocessing_api.sessions import get_session_repository

ACTIVITY_TOPIC = "cogniflow.behavioral-activity.v1"
FEATURE_TOPIC = "cogniflow.behavioral-features.v1"
DLQ_TOPIC = "cogniflow.dead-letter.v1"


def _lifecycle(session_id: str, event_type: str, sequence: int, when: datetime) -> dict:
    return {
        "event_id": str(uuid4()), "session_id": session_id, "event_time": when.isoformat(),
        "ingested_at": datetime.now(UTC).isoformat(), "source": "local_flink_smoke",
        "producer_version": "1.0.0", "idempotency_key": f"{session_id}:lifecycle:{sequence}",
        "event_type": event_type, "sequence": sequence, "session_kind": "programming",
        "privacy_mode": "behavioral",
    }


def _expect(response: httpx.Response, expected: int, operation: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{operation} failed with HTTP {response.status_code}")


def _activity(session_id: str, window: dict, suffix: str) -> dict:
    return {
        "event_id": str(uuid4()),
        "session_id": session_id,
        "event_time": window["window_end"],
        "ingested_at": datetime.now(UTC).isoformat(),
        "source": "local_flink_smoke",
        "producer_version": "1.0.0",
        "idempotency_key": f"{session_id}:activity:{suffix}",
        "event_type": "behavioral.window",
        **window,
        "feature_cutoff": window["window_end"],
        "active_seconds": 240,
        "idle_seconds": 60,
        "keyboard_event_count": 12,
        "pointer_event_count": 3,
        "application_switch_count": 2,
        "build_count": None,
        "test_count": None,
    }


async def _prepare(repository: FocusSessionRepository, api_key: str) -> tuple[str, dict, dict]:
    async def dependency() -> FocusSessionRepository:
        return repository

    app.dependency_overrides[get_session_repository] = dependency
    session_id = f"flink-smoke-{uuid4()}"
    start = datetime.now(UTC) - timedelta(minutes=20)
    headers = {"x-api-key": api_key}
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
            response = await client.post(
                "/sessions", json=_lifecycle(session_id, "session.started", 1, start),
                headers=headers,
            )
            _expect(response, 201, "create session")
            response = await client.post(
                f"/sessions/{session_id}/transitions",
                json=_lifecycle(session_id, "session.completed", 2, start + timedelta(minutes=10)),
                headers=headers,
            )
            _expect(response, 200, "complete session")
            response = await client.get(f"/sessions/{session_id}", headers=headers)
            _expect(response, 200, "read session")
            windows = response.json()["completed_windows"]
            older, newer = _activity(session_id, windows[0], "older"), _activity(
                session_id, windows[1], "newer"
            )
            response = await client.post(
                f"/sessions/{session_id}/activity-windows", json=newer, headers=headers
            )
            _expect(response, 201, "submit newer activity")
            response = await client.post(
                f"/sessions/{session_id}/activity-windows", json=newer, headers=headers
            )
            _expect(response, 200, "retry newer activity")
    finally:
        app.dependency_overrides.clear()
    return session_id, older, newer


def _consumer(brokers: str, topic: str) -> Consumer:
    consumer = Consumer({
        "bootstrap.servers": brokers,
        "group.id": f"cogniflow-flink-smoke-{uuid4()}",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([topic])
    return consumer


def _matching_json(consumer: Consumer, field: str, value: str, timeout: float = 20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = consumer.poll(0.5)
        if message is None:
            continue
        if message.error():
            raise RuntimeError("Kafka consumer returned an error")
        raw = message.value()
        if raw is None:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if payload.get(field) == value:
            return payload, message.partition(), message.offset()
    raise RuntimeError(f"matching event was not consumed from {consumer.list_topics().orig_broker_name}")


def _wait_redis(client: redis.Redis, key: str, source_event_id: str) -> BehavioralFeatureRecord:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        value = client.get(key)
        if value:
            record = BehavioralFeatureRecord.model_validate_json(value)
            if str(record.source_event_id) == source_event_id:
                return record
        time.sleep(0.25)
    raise RuntimeError("matching behavioral feature was not stored in Redis")


async def _submit_older(repository: FocusSessionRepository, api_key: str, session_id: str,
                        older: dict) -> None:
    async def dependency() -> FocusSessionRepository:
        return repository

    app.dependency_overrides[get_session_repository] = dependency
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://local") as client:
            response = await client.post(
                f"/sessions/{session_id}/activity-windows", json=older,
                headers={"x-api-key": api_key},
            )
            _expect(response, 201, "submit older activity")
    finally:
        app.dependency_overrides.clear()


def run(database: Path, brokers: str, redis_url: str) -> dict[str, object]:
    if database.exists():
        raise RuntimeError("smoke-test database already exists; use a fresh path")
    api_key = secrets.token_urlsafe(32)
    os.environ["COGNIFLOW_API_KEY"] = api_key
    os.environ["KAFKA_BOOTSTRAP_SERVERS"] = brokers
    repository = FocusSessionRepository(database)
    session_id, older, newer = asyncio.run(_prepare(repository, api_key))
    publisher = KafkaPublisher()
    published_initial = publish_pending(repository, publisher, limit=25)

    feature_consumer = _consumer(brokers, FEATURE_TOPIC)
    redis_client = redis.Redis.from_url(redis_url, socket_timeout=2, decode_responses=False)
    redis_key = f"cogniflow:behavioral-features:v1:{session_id}"
    try:
        feature_payload, feature_partition, feature_offset = _matching_json(
            feature_consumer, "source_event_id", newer["event_id"]
        )
        live = _wait_redis(redis_client, redis_key, newer["event_id"])
        expected = behavioral_features(BehavioralActivityEvent.model_validate(newer))
        kafka_feature = BehavioralFeatureRecord.model_validate(feature_payload)
        differences = [
            name for name in BehavioralFeatureRecord.model_fields
            if getattr(live, name) != getattr(expected, name)
            or getattr(kafka_feature, name) != getattr(expected, name)
        ]
        if differences:
            raise RuntimeError(f"Flink/Redis projection differs in fields: {differences}")

        publisher.publish_bytes(
            BehavioralActivityEvent.model_validate(newer).model_dump_json().encode(),
            session_id.encode(), ACTIVITY_TOPIC,
        )
        time.sleep(4)
        if BehavioralFeatureRecord.model_validate_json(redis_client.get(redis_key)) != live:
            raise RuntimeError("duplicate replay changed the Redis feature")

        asyncio.run(_submit_older(repository, api_key, session_id, older))
        if publish_pending(repository, publisher, limit=25) != 1:
            raise RuntimeError("older activity outbox was not acknowledged")
        dlq_consumer = _consumer(brokers, DLQ_TOPIC)
        try:
            late_payload, dlq_partition, dlq_offset = _matching_json(
                dlq_consumer, "event_id", older["event_id"]
            )
        finally:
            dlq_consumer.close()
        if late_payload.get("reason") != "event_time_behind_watermark":
            raise RuntimeError("older event was not quarantined as late")
        if BehavioralFeatureRecord.model_validate_json(redis_client.get(redis_key)) != live:
            raise RuntimeError("older event replaced the fresher Redis feature")
    finally:
        feature_consumer.close()
        redis_client.close()
    return {
        "status": "passed", "session_id": session_id,
        "newer_event_id": newer["event_id"], "older_event_id": older["event_id"],
        "window_id": newer["window_id"], "feature_cutoff": newer["feature_cutoff"],
        "feature_partition": feature_partition, "feature_offset": feature_offset,
        "dlq_partition": dlq_partition, "dlq_offset": dlq_offset,
        "published_initial": published_initial, "duplicate_redis_unchanged": True,
        "older_redis_rejected": True, "optional_counts_null": True,
    }


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("preprocessing_api.observability").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--brokers", default="127.0.0.1:29092")
    parser.add_argument(
        "--redis-url", default="redis://:local-development-only@127.0.0.1:6379/0"
    )
    args = parser.parse_args()
    print(json.dumps(run(args.database, args.brokers, args.redis_url), sort_keys=True))


if __name__ == "__main__":
    main()
