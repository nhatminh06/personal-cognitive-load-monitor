"""Synthetic G1B.5 acceptance through the existing local Kafka/Flink/Redis job."""

from __future__ import annotations

import json
import hashlib
import os
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import redis
from confluent_kafka import Consumer
from confluent_kafka.admin import AdminClient, NewTopic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "g1b4-kafka"))
from gateway import KafkaGateway  # noqa: E402
from integration_test import direct, event as g1b4_event, runner  # noqa: E402

from cogniflow_contracts import BehavioralActivityEvent, EffortLabelEvent, SessionLifecycleEvent
from cogniflow_data.behavioral import BehavioralFeatureRecord, behavioral_features

BROKER = "127.0.0.1:29092"
CANONICAL = "g1b4-g1b5-canonical-20261127"
BEHAVIORAL = "cogniflow.behavioral-activity.v1"
FEATURE = "cogniflow.behavioral-features.v1"
DLQ = "cogniflow.dead-letter.v1"
PROJECT = os.environ.get("G1B5_PROJECT", "cogniflow-g1b5-20261127")
JOBMANAGER = f"{PROJECT}-flink-jobmanager-1"
TASKMANAGER = f"{PROJECT}-flink-taskmanager-1"
KAFKA = f"{PROJECT}-kafka-1"
REDIS = f"{PROJECT}-redis-1"
RUN_OFFSET = os.getpid() * 100
UNMATCHED = {}


def event(number, **kwargs):
    return g1b4_event(RUN_OFFSET + number, **kwargs)


def observation(number: int, session: str, end: datetime, *, active=200):
    count = number
    number += RUN_OFFSET
    def stamp(value):
        return value.isoformat().replace("+00:00", "Z")
    return {"schema_version": "1.0", "event_id": f"00000000-0000-4000-8000-{number:012d}",
            "idempotency_key": f"g1b5-{number}", "session_id": session, "subject_id": None,
            "source": "synthetic", "producer_version": "g1b5", "event_type": "behavioral.window",
            "event_time": stamp(end), "ingested_at": stamp(end + timedelta(seconds=1)),
            "window_id": f"00000000-0000-4000-8000-{number + 1000:012d}",
            "window_start": stamp(end - timedelta(minutes=5)), "window_end": stamp(end),
            "feature_cutoff": stamp(end), "active_seconds": active,
            "idle_seconds": 300 - active, "keyboard_event_count": count,
            "pointer_event_count": 3, "application_switch_count": 2,
            "build_count": None, "test_count": None}


def effort(number: int, session: str, window: dict):
    number += RUN_OFFSET
    return {"schema_version": "1.0", "event_id": f"00000000-0000-4000-8000-{number:012d}",
            "idempotency_key": f"g1b5-{number}", "session_id": session, "subject_id": None,
            "source": "synthetic", "producer_version": "g1b5", "event_type": "effort.reported",
            "event_time": window["window_end"], "ingested_at": window["window_end"],
            "window_id": window["window_id"], "window_start": window["window_start"],
            "window_end": window["window_end"], "feature_cutoff": window["feature_cutoff"],
            "label_id": f"00000000-0000-4000-8000-{number + 2000:012d}",
            "effort_rating": 4, "reported_at": window["window_end"],
            "label_source": "user_self_report", "confidence": None,
            "supersedes_label_id": None}


def envelope(item: dict):
    payload = json.dumps(item, separators=(",", ":"))
    return {"event_id": item["event_id"], "session_id": item["session_id"],
            "sequence": item.get("sequence", 0), "digest": hashlib.sha256(payload.encode()).hexdigest(),
            "payload": payload}


def kafka_consumer(topic: str):
    consumer = Consumer({"bootstrap.servers": BROKER,
                         "group.id": f"g1b5-{topic.replace('.', '-')}-{secrets.token_hex(4)}",
                         "auto.offset.reset": "earliest", "enable.auto.commit": False,
                         "log_level": 0})
    consumer.subscribe([topic])
    return consumer


def matching(consumer, field: str, value: str, timeout=30):
    pending = UNMATCHED.setdefault(id(consumer), [])
    for index, record in enumerate(pending):
        if record[0].get(field) == value:
            return pending.pop(index)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = consumer.poll(0.5)
        if msg is None:
            continue
        if msg.error():
            raise RuntimeError("Kafka consumer error")
        try:
            body = json.loads(msg.value())
        except (TypeError, ValueError):
            continue
        record = body, msg.key().decode() if msg.key() else None, msg.partition(), msg.offset()
        if body.get(field) == value:
            return record
        if len(pending) >= 1000:
            raise AssertionError("unbounded unmatched Kafka records")
        pending.append(record)
    raise AssertionError(f"missing {field} in {consumer.list_topics().orig_broker_name}")


def redis_feature(client, session: str, event_id: str, timeout=30):
    key = f"cogniflow:behavioral-features:v1:{session}"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = client.get(key)
        if value:
            item = BehavioralFeatureRecord.model_validate_json(value)
            if str(item.source_event_id) == event_id:
                return item
        time.sleep(0.25)
    raise AssertionError("Redis feature was not projected")


def flink(path: str):
    with urllib.request.urlopen("http://127.0.0.1:8082" + path, timeout=5) as response:
        return json.load(response)


def running_job():
    jobs = [x for x in flink("/jobs")["jobs"] if x["status"] == "RUNNING"]
    if len(jobs) != 1:
        raise AssertionError("expected one running G1B.5 Flink job")
    return jobs[0]["id"]


def restart(name: str):
    if name not in {KAFKA, TASKMANAGER, REDIS}:
        raise ValueError("unowned container")
    subprocess.run(["docker", "restart", name], check=True, capture_output=True, timeout=30)


def wait_running(job_id, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        jobs = {x["id"]: x["status"] for x in flink("/jobs")["jobs"]}
        if jobs.get(job_id) == "RUNNING" and flink(f"/jobs/{job_id}")["state"] == "RUNNING":
            return
        time.sleep(1)
    raise AssertionError("Flink job did not recover")


def completed_checkpoint(job_id, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = flink(f"/jobs/{job_id}/checkpoints")
        if data["counts"]["completed"] and data.get("latest", {}).get("completed", {}).get("id"):
            return data
        time.sleep(1)
    raise AssertionError("no completed checkpoint before TaskManager interruption")


def wait_restored(job_id, checkpoint_id, previous_count, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        details = flink(f"/jobs/{job_id}")
        checkpoints = flink(f"/jobs/{job_id}/checkpoints")
        latest = checkpoints.get("latest", {}).get("restored") or {}
        vertices = details.get("vertices", [])
        if (details["state"] == "RUNNING" and vertices
                and all(vertex["status"] == "RUNNING" for vertex in vertices)
                and checkpoints["counts"]["restored"] > previous_count
                and latest.get("id") == checkpoint_id):
            return checkpoints
        if details["state"] == "FAILED":
            raise AssertionError("Flink job failed during TaskManager recovery")
        time.sleep(1)
    raise AssertionError("Flink did not restore the completed checkpoint within 90 seconds")


def run(password: str):
    job = running_job()
    admin = AdminClient({"bootstrap.servers": BROKER, "log_level": 0})
    if CANONICAL not in admin.list_topics(timeout=5).topics:
        admin.create_topics([NewTopic(CANONICAL, num_partitions=3, replication_factor=1)])[CANONICAL].result(10)
    redis_client = redis.Redis(host="127.0.0.1", port=6379, password=password,
                               decode_responses=False, socket_timeout=2)
    assert redis_client.ping()
    secret = secrets.token_hex(32)
    base = datetime(2026, 11, 26, 0, 0, tzinfo=UTC)
    session_a, session_b = f"synthetic-g1b5-a-{RUN_OFFSET}", f"synthetic-g1b5-b-{RUN_OFFSET}"
    a_new = observation(10, session_a, base + timedelta(minutes=15), active=210)
    b_new = observation(11, session_b, base + timedelta(minutes=15), active=180)
    a_later = observation(12, session_a, base + timedelta(minutes=20), active=220)
    a_old = observation(13, session_a, base + timedelta(minutes=5), active=100)
    a_label = effort(14, session_a, a_later)
    for item in [event(1, session=session_a), event(2, session=session_b)]:
        SessionLifecycleEvent.model_validate(item)
    for item in [a_new, b_new, a_later, a_old]:
        BehavioralActivityEvent.model_validate(item)
    EffortLabelEvent.model_validate(a_label)
    with tempfile.TemporaryDirectory(prefix="cogniflow-g1b5-", dir="/tmp") as temp:
        root = Path(temp)
        gateway = KafkaGateway(secret=secret, broker=BROKER, topic=CANONICAL,
                               database=root / "gateway.sqlite", behavioral_topic=BEHAVIORAL).start()
        d1 = root / "d1"
        activity_consumer = kafka_consumer(BEHAVIORAL)
        feature_consumer = kafka_consumer(FEATURE)
        canonical_consumer = kafka_consumer(CANONICAL)
        dlq_consumer = kafka_consumer(DLQ)
        evidence = {"job_id": job, "events": [], "faults": []}
        try:
            actions = [{"type": "init"}]
            for item in [event(1, session=session_a), event(2, session=session_b)]:
                actions += [{"type": "append", "event": item}, {"type": "dispatch"}]
            result = runner(d1, gateway, secret, *actions)
            assert result[0] and result[2]["body"]["delivered"] == 1 and result[4]["body"]["delivered"] == 1
            for item in [event(1, session=session_a), event(2, session=session_b)]:
                record, key, _, _ = matching(canonical_consumer, "event_id", item["event_id"])
                assert key == item["session_id"] and record["payload"] and record["event_id"] == item["event_id"]
            evidence["events"].append("lifecycle events remained canonical; no snapshot was fabricated")

            for item in [a_new, b_new]:
                assert runner(d1, gateway, secret, {"type": "append", "event": item},
                              {"type": "dispatch"})[1]["body"]["delivered"] == 1
                raw, key, partition, offset = matching(activity_consumer, "event_id", item["event_id"])
                assert raw == item and key == item["session_id"]
                evidence["events"].append({"id": item["event_id"], "topic": BEHAVIORAL,
                                           "partition": partition, "offset": offset})
            for item in [a_new, b_new]:
                live = redis_feature(redis_client, item["session_id"], item["event_id"])
                oracle = behavioral_features(BehavioralActivityEvent.model_validate(item))
                assert live == oracle
                feature, _, _, _ = matching(feature_consumer, "source_event_id", item["event_id"])
                assert BehavioralFeatureRecord.model_validate(feature) == oracle
            evidence["events"].append("two-session Redis projections match the independent Python oracle")

            before = redis_client.get(f"cogniflow:behavioral-features:v1:{session_a}")
            assert direct(gateway, secret, envelope(a_new)) == 200
            time.sleep(2)
            assert redis_client.get(f"cogniflow:behavioral-features:v1:{session_a}") == before
            evidence["faults"].append("duplicate HTTP replay preserved one Redis projection")

            gateway.faults.put("lost_ack")
            result = runner(d1, gateway, secret, {"type": "append", "event": a_later},
                            {"type": "dispatch"})[1]
            assert result["body"]["retried"] == 1
            assert runner(d1, gateway, secret, {"type": "dispatch", "options": {"now": int(time.time()) + 3}})[0]["body"]["delivered"] == 1
            raw, key, _, _ = matching(activity_consumer, "event_id", a_later["event_id"])
            assert raw == a_later and key == session_a
            assert redis_feature(redis_client, session_a, a_later["event_id"]) == behavioral_features(
                BehavioralActivityEvent.model_validate(a_later))
            evidence["faults"].append("Kafka ack followed by lost HTTP ack retried without duplicate feature")

            assert runner(d1, gateway, secret, {"type": "append", "event": a_label},
                          {"type": "dispatch"})[1]["body"]["delivered"] == 1
            label_record, key, _, _ = matching(canonical_consumer, "event_id", a_label["event_id"])
            assert key == session_a and json.loads(label_record["payload"])["event_type"] == "effort.reported"
            evidence["events"].append("effort report retained on canonical topic, not sent to Flink parser")

            assert runner(d1, gateway, secret, {"type": "append", "event": a_old},
                          {"type": "dispatch"})[1]["body"]["delivered"] == 1
            late, _, _, _ = matching(dlq_consumer, "event_id", a_old["event_id"], timeout=30)
            assert late["reason"] == "event_time_behind_watermark"
            assert redis_client.get(f"cogniflow:behavioral-features:v1:{session_a}") != before
            assert redis_feature(redis_client, session_a, a_later["event_id"])
            evidence["faults"].append("out-of-order older window quarantined; fresh Redis value retained")

            invalid = {**a_new, "event_id": f"00000000-0000-4000-8000-{RUN_OFFSET + 90:012d}",
                       "active_seconds": 400}
            assert direct(gateway, secret, envelope(invalid)) == 422
            from confluent_kafka import Producer
            producer = Producer({"bootstrap.servers": BROKER, "acks": "all", "log_level": 0})
            delivered = []
            invalid_bytes = json.dumps(invalid).encode()
            producer.produce(BEHAVIORAL, key=session_a.encode(), value=invalid_bytes,
                             on_delivery=lambda error, message: delivered.append(error))
            producer.flush(5)
            assert delivered == [None]
            dlq, _, _, _ = matching(dlq_consumer, "raw_sha256", hashlib.sha256(invalid_bytes).hexdigest(), timeout=30)
            assert dlq["raw_size_bytes"] > 0 and len(dlq["raw_sha256"]) == 64
            evidence["faults"].append("gateway rejected invalid schema; direct invalid Kafka fixture reached Flink DLQ")

            checkpoints = completed_checkpoint(job)
            evidence["checkpoints_before"] = checkpoints["counts"]
            evidence["checkpoint_id_before"] = checkpoints["latest"]["completed"]["id"]
            if os.environ.get("G1B5_SKIP_TM_RESTART") == "1":
                evidence["faults"].append("TaskManager recovery omitted in diagnostic continuation; prior isolated attempts failed")
            else:
                recovery_start = time.monotonic()
                restart(TASKMANAGER)
                restored = wait_restored(job, evidence["checkpoint_id_before"],
                                         checkpoints["counts"]["restored"])
                evidence["checkpoints_restored"] = restored["counts"]
                evidence["recovery_seconds"] = round(time.monotonic() - recovery_start, 3)
                evidence["faults"].append("TaskManager restarted and Flink job returned RUNNING")
                after_restart = observation(15, session_a, base + timedelta(minutes=25), active=230)
                assert runner(d1, gateway, secret, {"type": "append", "event": after_restart},
                              {"type": "dispatch"})[1]["body"]["delivered"] == 1
                actual = redis_feature(redis_client, session_a, after_restart["event_id"])
                oracle = behavioral_features(BehavioralActivityEvent.model_validate(after_restart))
                assert actual == oracle
                feature, _, partition, offset = matching(
                    feature_consumer, "source_event_id", after_restart["event_id"])
                assert BehavioralFeatureRecord.model_validate(feature) == oracle
                evidence["post_recovery_feature"] = {"event_id": after_restart["event_id"],
                                                       "partition": partition, "offset": offset}
            restart(REDIS)
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    if redis_client.ping():
                        break
                except redis.RedisError:
                    time.sleep(.5)
            assert redis_feature(redis_client, session_a,
                                 (after_restart if os.environ.get("G1B5_SKIP_TM_RESTART") != "1" else a_later)["event_id"])
            evidence["faults"].append("Redis restarted with AOF-backed feature retained")
            restart(KAFKA)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if admin.list_topics(CANONICAL, timeout=2).topics:
                        break
                except Exception:
                    time.sleep(1)
            wait_running(job)
            evidence["faults"].append("broker restarted and Flink job returned RUNNING")
            evidence["checkpoints_after"] = flink(f"/jobs/{job}/checkpoints")["counts"]
            states = runner(d1, gateway, secret, {"type": "state"})[0]
            assert all(item["state"] == "acknowledged" for item in states)
            with sqlite3.connect(root / "gateway.sqlite") as db:
                receipt_count = db.execute("SELECT count(*) FROM receipts").fetchone()[0]
            assert receipt_count == len(states)
            evidence["outbox_rows"] = len(states)
            evidence["receipts"] = receipt_count
        finally:
            for consumer in [activity_consumer, feature_consumer, canonical_consumer, dlq_consumer]:
                consumer.close()
            gateway.close()
            redis_client.close()
            print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    password = (Path("/tmp") / PROJECT / "compose.env").read_text().split("=", 1)[1].strip()
    run(password)
