"""Bounded synthetic Kafka consumer with durable logical deduplication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path

from confluent_kafka import Consumer, KafkaException


class DurableConsumer:
    def __init__(self, *, broker: str, topic: str, database: Path, group: str):
        if not broker.startswith("127.0.0.1:") or not topic.startswith("g1b4-") or not group.startswith("g1b4-"):
            raise ValueError("unsafe consumer configuration")
        self.topic, self.database = topic, Path(database)
        self.consumer = Consumer({"bootstrap.servers": broker, "group.id": group,
                                  "enable.auto.commit": False, "auto.offset.reset": "earliest",
                                  "socket.timeout.ms": 2000, "error_cb": lambda _error: None,
                                  "log_level": 0})
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS processed (
                  event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, session_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records (
                  id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, partition_id INTEGER NOT NULL,
                  offset_id INTEGER NOT NULL, result TEXT NOT NULL,
                  UNIQUE(partition_id,offset_id));
                CREATE TABLE IF NOT EXISTS processing_attempts (
                  id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, result TEXT NOT NULL);
            """)
        self.consumer.subscribe([topic])

    def close(self):
        self.consumer.close()

    def consume(self, *, max_records: int, timeout: float = 8, crash_before_commit=False):
        if not 1 <= max_records <= 100 or not 0 < timeout <= 30:
            raise ValueError("unbounded consume request")
        deadline, count = time.monotonic() + timeout, 0
        while count < max_records and time.monotonic() < deadline:
            msg = self.consumer.poll(min(0.2, max(0.001, deadline - time.monotonic())))
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())
            item = json.loads(msg.value())
            if not isinstance(item, dict) or set(item) != {"event_id", "session_id", "sequence", "digest", "payload"} or not isinstance(item["payload"], str) or len(item["payload"].encode()) > 4096:
                raise ValueError("invalid Kafka envelope")
            event = json.loads(item["payload"])
            if not isinstance(event, dict) or not isinstance(item["session_id"], str) or not (1 <= len(item["session_id"]) <= 128):
                raise ValueError("invalid Kafka event")
            digest = hashlib.sha256(item["payload"].encode()).hexdigest()
            try:
                uuid.UUID(item["event_id"])
            except (ValueError, TypeError, KeyError):
                raise ValueError("invalid Kafka event ID") from None
            lifecycle = event.get("event_type") in {"session.started", "session.paused", "session.resumed", "session.completed", "session.cancelled"}
            if (not isinstance(item["digest"], str) or item["digest"] != digest or item["event_id"] != event.get("event_id") or
                    item["session_id"] != event.get("session_id") or
                    msg.key() != item["session_id"].encode() or event.get("schema_version") != "1.0" or
                    event.get("source") != "synthetic" or event.get("subject_id") is not None or
                    type(item["sequence"]) is not int or item["sequence"] < 0 or
                    event.get("sequence", 0) != item["sequence"] or
                    (lifecycle and item["sequence"] < 1) or
                    (not lifecycle and (event.get("event_type") not in {"behavioral.window", "effort.reported"} or item["sequence"] != 0))):
                raise ValueError("invalid Kafka event")
            with closing(sqlite3.connect(self.database, timeout=2)) as db, db:
                prior = db.execute("SELECT digest FROM processed WHERE event_id=?", (item["event_id"],)).fetchone()
                if prior and prior[0] != digest:
                    raise ValueError("conflicting Kafka event ID")
                if not prior:
                    db.execute("INSERT INTO processed VALUES (?,?,?)", (item["event_id"], digest, item["session_id"]))
                db.execute("INSERT OR IGNORE INTO records(event_id,partition_id,offset_id,result) VALUES (?,?,?,?)",
                           (item["event_id"], msg.partition(), msg.offset(), "duplicate" if prior else "new"))
                db.execute("INSERT INTO processing_attempts(event_id,result) VALUES (?,?)",
                           (item["event_id"], "duplicate" if prior else "new"))
            count += 1
            if crash_before_commit:
                return count
            self.consumer.commit(message=msg, asynchronous=False)
        return count

    def counts(self):
        with closing(sqlite3.connect(self.database)) as db:
            return dict(zip(("records", "logical", "duplicates", "processing_attempts"), db.execute("""
                SELECT (SELECT count(*) FROM records),(SELECT count(*) FROM processed),
                       (SELECT count(*) FROM processing_attempts WHERE result='duplicate'),
                       (SELECT count(*) FROM processing_attempts)
            """).fetchone()))


def reconcile(expected_ids, receipt_ids, processed_ids, attempt_ids):
    """Compare stable logical IDs; duplicate Kafka attempts are reported separately."""
    groups = (expected_ids, receipt_ids, processed_ids, attempt_ids)
    if any(not isinstance(group, (list, tuple, set)) or len(group) > 1000 or
           any(not isinstance(item, str) for item in group) for group in groups):
        raise ValueError("unbounded reconciliation input")
    expected, receipts, processed = map(set, groups[:3])
    seen = set()
    duplicates = set()
    for event_id in attempt_ids:
        if event_id in seen:
            duplicates.add(event_id)
        seen.add(event_id)
    return {"missing_receipts": sorted(expected - receipts),
            "missing_processed": sorted(receipts - processed),
            "unexpected_receipts": sorted(receipts - expected),
            "unexpected_processed": sorted(processed - receipts),
            "duplicate_attempt_ids": sorted(duplicates)}
