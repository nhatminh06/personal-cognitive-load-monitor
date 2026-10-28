"""Bounded at-least-once delivery for the focus-session SQLite outbox."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol

from prometheus_client import Counter, Gauge

from cogniflow_data.kafka import PublishError
from cogniflow_sessions.repository import FocusSessionRepository

OUTBOX_PENDING = Gauge("cogniflow_focus_outbox_pending", "Unpublished focus-session events.")
OUTBOX_DELIVERIES = Counter(
    "cogniflow_focus_outbox_deliveries_total", "Focus outbox delivery outcomes.", ["result"]
)


class BytesPublisher(Protocol):
    def publish_bytes(self, value: bytes, key: bytes, topic: str) -> None: ...


def publish_pending(
    repository: FocusSessionRepository, publisher: BytesPublisher, *, limit: int = 25
) -> int:
    """Publish one bounded batch, stopping at the first unacknowledged record."""

    rows = repository.pending_outbox(limit)
    OUTBOX_PENDING.set(len(rows))
    published = 0
    for row in rows:
        payload = json.loads(row["event_json"])
        try:
            publisher.publish_bytes(
                row["event_json"].encode(), payload["session_id"].encode(), row["topic"]
            )
        except PublishError:
            repository.mark_failed(row["event_id"], datetime.now(UTC))
            OUTBOX_DELIVERIES.labels("failed").inc()
            break
        repository.mark_published(row["event_id"], datetime.now(UTC))
        OUTBOX_DELIVERIES.labels("published").inc()
        published += 1
    OUTBOX_PENDING.set(len(repository.pending_outbox(100)))
    return published
