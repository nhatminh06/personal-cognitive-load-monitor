"""Real-Kafka Flink duplicate and canonical-consumer restart checks for G1B.5."""

import json
import os
import secrets
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import redis
from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g1b4-kafka"))
from consumer import DurableConsumer  # noqa: E402

BROKER = "127.0.0.1:29092"
BEHAVIORAL = "cogniflow.behavioral-activity.v1"
CANONICAL = "g1b4-g1b5-canonical-20261127"


def records(topic):
    consumer = Consumer({"bootstrap.servers": BROKER, "group.id": "g1b5-read-" + secrets.token_hex(4),
                         "auto.offset.reset": "earliest", "enable.auto.commit": False,
                         "log_level": 0})
    partitions = AdminClient({"bootstrap.servers": BROKER, "log_level": 0}).list_topics(topic, timeout=5).topics[topic].partitions
    consumer.assign([TopicPartition(topic, partition, 0) for partition in partitions])
    items, deadline, idle = [], time.monotonic() + 12, None
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(.2)
            if message is None:
                if idle is not None and time.monotonic() - idle > 1:
                    break
                continue
            if message.error():
                raise RuntimeError("Kafka read error")
            items.append(message)
            idle = time.monotonic()
    finally:
        consumer.close()
    return items


def publish(topic, key, value):
    producer = Producer({"bootstrap.servers": BROKER, "acks": "all", "enable.idempotence": True,
                         "message.timeout.ms": 3000, "log_level": 0})
    outcome = []
    producer.produce(topic, key=key, value=value,
                     on_delivery=lambda error, _message: outcome.append(error))
    producer.flush(5)
    assert outcome == [None]


def duplicate_metric(job):
    with urllib.request.urlopen(f"http://127.0.0.1:8082/jobs/{job}", timeout=5) as response:
        vertices = json.load(response)["vertices"]
    for vertex in vertices:
        path = f"/jobs/{job}/vertices/{vertex['id']}/subtasks/0/metrics"
        with urllib.request.urlopen("http://127.0.0.1:8082" + path, timeout=5) as response:
            names = {item["id"] for item in json.load(response)}
        name = "KeyedProcess.duplicate_behavioral_events_total"
        if name in names:
            with urllib.request.urlopen("http://127.0.0.1:8082" + path + "?get=" + name,
                                        timeout=5) as response:
                return int(json.load(response)[0]["value"])
    raise AssertionError("Flink duplicate metric unavailable")


def run():
    project = os.environ.get("G1B5_PROJECT", "cogniflow-g1b5-20261127")
    filename = os.environ.get("G1B5_EVIDENCE_FILE", "diagnostic-evidence.json")
    evidence = json.loads((Path("/tmp") / project / filename).read_text())
    target = next(item["id"] for item in evidence["events"] if isinstance(item, dict))
    activity = records(BEHAVIORAL)
    target_record = next(message for message in activity if json.loads(message.value())["event_id"] == target)
    session = target_record.key().decode()
    password = (Path("/tmp") / project / "compose.env").read_text().split("=", 1)[1].strip()
    client = redis.Redis(host="127.0.0.1", port=6379, password=password, socket_timeout=2)
    key = f"cogniflow:behavioral-features:v1:{session}"
    before = client.get(key)
    assert before
    metric_before = duplicate_metric(evidence["job_id"])
    publish(BEHAVIORAL, target_record.key(), target_record.value())
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and duplicate_metric(evidence["job_id"]) <= metric_before:
        time.sleep(.5)
    metric_after = duplicate_metric(evidence["job_id"])
    assert metric_after >= metric_before + 1
    assert client.get(key) == before
    client.close()

    canonical = records(CANONICAL)
    assert len(canonical) == 3
    with tempfile.TemporaryDirectory(prefix="cogniflow-g1b5-consumer-", dir="/tmp") as temp:
        database = Path(temp) / "consumer.sqlite"
        group = "g1b4-g1b5-post-" + secrets.token_hex(4)
        consumer = DurableConsumer(broker=BROKER, topic=CANONICAL, database=database, group=group)
        try:
            assert consumer.consume(max_records=3, timeout=12) == 3
            assert consumer.counts()["logical"] == 3
        finally:
            consumer.close()
        publish(CANONICAL, canonical[0].key(), canonical[0].value())
        consumer = DurableConsumer(broker=BROKER, topic=CANONICAL, database=database, group=group)
        try:
            assert consumer.consume(max_records=1, timeout=12) == 1
            counts = consumer.counts()
        finally:
            consumer.close()
    assert counts == {"records": 4, "logical": 3, "duplicates": 1, "processing_attempts": 4}
    print(json.dumps({"flink_duplicate_metric_before": metric_before,
                      "flink_duplicate_metric_after": metric_after,
                      "redis_unchanged": True, "canonical_consumer_after_restart": counts,
                      "behavioral_records_after_duplicate": len(records(BEHAVIORAL))}, indent=2))


if __name__ == "__main__":
    run()
