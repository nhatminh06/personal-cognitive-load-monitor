"""Bounded Kafka producer and restart-safe consumer primitives."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import deque
from collections.abc import Callable
from typing import Any, Protocol

from cogniflow_data.events import DEAD_LETTER_TOPIC, SESSION_TOPIC, SessionEvent


class PublishError(RuntimeError):
    """Kafka did not durably acknowledge a message."""


class EventPublisher(Protocol):
    def publish(self, event: SessionEvent, topic: str = SESSION_TOPIC) -> None: ...


def _producer_config() -> dict[str, Any]:
    return {
        "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:29092"),
        "client.id": os.getenv("KAFKA_CLIENT_ID", "cogniflow-api"),
        "acks": "all",
        "enable.idempotence": True,
        "retries": 5,
        "retry.backoff.ms": 200,
        "delivery.timeout.ms": int(os.getenv("KAFKA_DELIVERY_TIMEOUT_MS", "5000")),
        "request.timeout.ms": int(os.getenv("KAFKA_REQUEST_TIMEOUT_MS", "3000")),
    }


class KafkaPublisher:
    """Publish only after an all-replicas delivery acknowledgment."""

    def __init__(self, producer: Any | None = None) -> None:
        if producer is None:
            try:
                from confluent_kafka import Producer
            except ImportError as exc:
                raise PublishError("Kafka client is not installed") from exc
            producer = Producer(_producer_config())
        self._producer = producer

    def publish(self, event: SessionEvent, topic: str = SESSION_TOPIC) -> None:
        self.publish_bytes(event.wire_bytes(), event.kafka_key(), topic)

    def publish_bytes(self, value: bytes, key: bytes, topic: str = SESSION_TOPIC) -> None:
        """Publish a raw test record with the same bounded acknowledgment policy."""

        failure: list[str] = []

        def delivered(error, _message) -> None:
            if error is not None:
                failure.append(str(error))

        try:
            self._producer.produce(
                topic,
                key=key,
                value=value,
                on_delivery=delivered,
            )
            remaining = self._producer.flush(5.0)
        except Exception as exc:
            raise PublishError("Kafka publish failed") from exc
        if remaining or failure:
            raise PublishError("Kafka did not acknowledge the event")


class RecentEventIds:
    """Bounded in-process duplicate filter; Kafka offsets remain the restart checkpoint."""

    def __init__(self, capacity: int = 10_000) -> None:
        self._ids: set[str] = set()
        self._order: deque[str] = deque()
        self._capacity = capacity

    def add(self, event_id: str) -> bool:
        if event_id in self._ids:
            return False
        self._ids.add(event_id)
        self._order.append(event_id)
        if len(self._order) > self._capacity:
            self._ids.remove(self._order.popleft())
        return True


class KafkaEventConsumer:
    """Consume with manual commits after handling or durable dead-letter publish."""

    def __init__(self, consumer: Any, dead_letter_publisher: Any) -> None:
        self._consumer = consumer
        self._dead_letter_publisher = dead_letter_publisher
        self._seen = RecentEventIds()
        self._stopped = threading.Event()

    def run(self, handler: Callable[[SessionEvent, Any], None], timeout: float = 1.0) -> None:
        while not self._stopped.is_set():
            message = self._consumer.poll(timeout)
            if message is None:
                continue
            if message.error():
                continue
            self.process_message(message, handler)

    def process_message(self, message: Any, handler: Callable[[SessionEvent, Any], None]) -> None:
        """Handle one message and commit only after success or durable quarantine."""

        try:
            event = SessionEvent.model_validate_json(message.value())
            if self._seen.add(str(event.event_id)):
                handler(event, message)
        except Exception as exc:
            raw_value = message.value()
            dead_letter = json.dumps(
                {
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "error_type": type(exc).__name__,
                    "raw_sha256": hashlib.sha256(raw_value).hexdigest(),
                    "raw_size_bytes": len(raw_value),
                }
            ).encode()
            self._dead_letter_publisher.produce(
                DEAD_LETTER_TOPIC, key=message.key(), value=dead_letter
            )
            if self._dead_letter_publisher.flush(5.0):
                return
        self._consumer.commit(message=message, asynchronous=False)

    def stop(self) -> None:
        self._stopped.set()
