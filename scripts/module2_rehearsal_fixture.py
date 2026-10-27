"""Publish a bounded fixture through FastAPI/Kafka and persist verified Bronze evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cogniflow_data.bronze import BronzeRecord, BronzeStore, KafkaPosition  # noqa: E402
from cogniflow_data.events import SESSION_TOPIC, SessionEvent  # noqa: E402
from preprocessing_api.main import app  # noqa: E402
from scripts.generate_session_events import event  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--session-id", default="rehearsal-batch")
    args = parser.parse_args()
    if args.count < 1 or args.count > 20:
        raise SystemExit("count must be between 1 and 20")

    from confluent_kafka import Consumer

    start = datetime.now(UTC).replace(microsecond=0)
    api_key = os.environ["COGNIFLOW_API_KEY"]
    responses = []
    with TestClient(app) as client:
        for index in range(args.count):
            item = event(index, random.Random(1000 + index), start, session_count=1, id_offset=10_000)
            item.session_id = args.session_id
            response = client.post("/events", json=item.model_dump(mode="json"), headers={"X-API-Key": api_key})
            response.raise_for_status()
            responses.append(response.json())

    consumer = Consumer(
        {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "group.id": f"rehearsal-bronze-{time.time_ns()}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([SESSION_TOPIC])
    records: list[BronzeRecord] = []
    deadline = time.monotonic() + 30
    try:
        while len(records) < args.count and time.monotonic() < deadline:
            message = consumer.poll(1)
            if message is None or message.error():
                continue
            item = SessionEvent.model_validate_json(message.value())
            if item.session_id != args.session_id:
                continue
            records.append(
                BronzeRecord(
                    item,
                    KafkaPosition(message.topic(), message.partition(), message.offset()),
                )
            )
    finally:
        consumer.close()
    if len(records) != args.count:
        raise RuntimeError(f"expected {args.count} broker records, received {len(records)}")

    store = BronzeStore()
    key = store.write_batch(records)
    replay_key = store.write_batch(records)
    if replay_key != key or len(store.read_batch(key)) != args.count:
        raise RuntimeError("Bronze replay/readback reconciliation failed")
    body = store._client.get_object(Bucket=store.bucket, Key=key)["Body"].read()  # noqa: SLF001
    print(
        json.dumps(
            {
                "api_statuses": [202 for _ in responses],
                "acknowledged_event_ids": [item["event_id"] for item in responses],
                "bronze_bucket": store.bucket,
                "bronze_key": key,
                "bronze_sha256": hashlib.sha256(body).hexdigest(),
                "bronze_records": len(records),
                "kafka_offsets": [record.kafka.__dict__ for record in records],
                "replay_idempotent": True,
                "source_records": args.count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
