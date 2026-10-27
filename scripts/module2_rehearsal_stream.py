"""Exercise isolated Flink windows, deduplication, lateness and Redis freshness."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cogniflow_data.events import FEATURE_TOPIC, SESSION_TOPIC  # noqa: E402
from cogniflow_data.kafka import KafkaPublisher  # noqa: E402
from preprocessing_api.main import app  # noqa: E402
from scripts.generate_session_events import event, event_bytes  # noqa: E402


STALE_WRITE = (
    "local old=redis.call('GET',KEYS[1]); if old then local o=cjson.decode(old); "
    "local n=cjson.decode(ARGV[1]); if o.feature_timestamp > n.feature_timestamp "
    "then return 0 end end; redis.call('SETEX',KEYS[1],ARGV[2],ARGV[1]); return 1"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-10-27T16:00:00+00:00")
    parser.add_argument("--session-id", default="rehearsal-stream-pr19")
    args = parser.parse_args()
    start = datetime.fromisoformat(args.start)
    publisher = KafkaPublisher()
    expected_focus = 0
    expected_distraction = 0
    for index in range(15):
        item = event(index, random.Random(42 + index), start, session_count=1, id_offset=20_000)
        item.session_id = args.session_id
        publisher.publish(item)
        if index in {4, 9, 14}:
            publisher.publish(item)
        if index < 10:
            expected_focus += item.payload.focus_minutes
            expected_distraction += item.payload.distraction_minutes

    trigger = event(0, random.Random(88), start, session_count=1, id_offset=50_000)
    trigger.session_id = args.session_id
    trigger.event_time = start + timedelta(seconds=30)
    publisher.publish(trigger)

    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "group.id": f"rehearsal-features-{time.time_ns()}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([FEATURE_TOPIC])
    matches = []
    deadline = time.monotonic() + 60
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(1)
            if message is None or message.error():
                continue
            raw_value = message.value()
            if raw_value is None:
                continue
            value = json.loads(raw_value)
            if value.get("session_id") == args.session_id:
                matches.append(value)
            if any(
                item.get("window_type") == "rolling"
                and item.get("window_start") == start.isoformat().replace("+00:00", "Z")
                for item in matches
            ):
                break
    finally:
        consumer.close()
    target = next(
        (
            item
            for item in matches
            if item.get("window_type") == "rolling"
            and item.get("window_start") == start.isoformat().replace("+00:00", "Z")
        ),
        None,
    )
    if target is None:
        raise RuntimeError("expected rolling window was not emitted")
    if (target["focus_minutes"], target["distraction_minutes"], target["event_count"]) != (
        expected_focus,
        expected_distraction,
        10,
    ):
        raise RuntimeError(
            "Flink window does not match the fixture oracle: "
            f"actual={(target['focus_minutes'], target['distraction_minutes'], target['event_count'])} "
            f"expected={(expected_focus, expected_distraction, 10)}"
        )

    invalid = event_bytes(0, 99, start, invalid=True, session_count=1, id_offset=30_000)
    publisher.publish_bytes(invalid, args.session_id.encode(), SESSION_TOPIC)
    late = event(0, random.Random(77), start, session_count=1, id_offset=40_000)
    late.session_id = args.session_id
    late.event_time = start + timedelta(seconds=1)
    publisher.publish(late)
    final_trigger = event(0, random.Random(89), start, session_count=1, id_offset=60_000)
    final_trigger.session_id = args.session_id
    final_trigger.event_time = start + timedelta(seconds=40)
    publisher.publish(final_trigger)
    time.sleep(3)

    import redis

    client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    key = f"cogniflow:features:v1:{args.session_id}"
    stored_value = client.get(key)
    if not isinstance(stored_value, str):
        raise RuntimeError("Redis feature record is missing")
    stored = json.loads(stored_value)
    stale = {**stored, "feature_timestamp": (start - timedelta(seconds=1)).isoformat()}
    stale_result = client.eval(STALE_WRITE, 1, key, json.dumps(stale), "3600")
    preserved_value = client.get(key)
    if not isinstance(preserved_value, str):
        raise RuntimeError("Redis feature record disappeared")
    if stale_result != 0 or json.loads(preserved_value)["feature_timestamp"] != stored["feature_timestamp"]:
        raise RuntimeError("Redis stale-write protection failed")
    with TestClient(app) as api:
        response = api.get(f"/features/{args.session_id}", headers={"X-API-Key": os.environ["COGNIFLOW_API_KEY"]})
    response.raise_for_status()
    print(
        json.dumps(
            {
                "api_status": response.status_code,
                "duplicates_published": 3,
                "invalid_published": 1,
                "late_published": 1,
                "oracle": {"focus_minutes": expected_focus, "distraction_minutes": expected_distraction, "event_count": 10},
                "redis_feature_timestamp": stored["feature_timestamp"],
                "stale_write_result": stale_result,
                "window": target,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
