"""Real broker-backed, synthetic-only G1B.4 qualification. Requires task-owned Kafka."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import statistics
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

from consumer import DurableConsumer, reconcile
from gateway import KafkaGateway

HERE = Path(__file__).resolve().parent
BROKER = "127.0.0.1:39094"
CONTAINER = "cogniflow-g1b4-kafka-20261127"
TOPIC = f"g1b4-synthetic-20261127-{os.getpid()}"
GROUP = f"g1b4-synthetic-20261127-{os.getpid()}"
DISPATCH_WALL_MS = []


def event(n, *, session=None, sequence=1, kind=None):
    sid = session or f"synthetic-g1b4-{n}"
    kind = kind or ("session.started" if sequence == 1 else "session.paused")
    return {
        "schema_version": "1.0", "event_id": f"00000000-0000-4000-8000-{n:012d}",
        "idempotency_key": f"g1b4-{n}", "session_id": sid, "subject_id": None,
        "source": "synthetic", "producer_version": "g1b4", "event_type": kind,
        "sequence": sequence, "session_kind": "study", "privacy_mode": "behavioral",
        "event_time": f"2026-11-26T00:00:{min(n, 59):02d}+00:00",
        "ingested_at": f"2026-11-26T00:00:{min(n, 59):02d}+00:00",
    }


def envelope(ev):
    payload = json.dumps(ev, separators=(",", ":"))
    return {"event_id": ev["event_id"], "session_id": ev["session_id"],
            "sequence": ev["sequence"], "digest": hashlib.sha256(payload.encode()).hexdigest(),
            "payload": payload}


def direct(gateway, secret, item, *, nonce=None, valid=True):
    body = json.dumps(item, separators=(",", ":")).encode()
    stamp, nonce = str(int(time.time())), nonce or str(uuid.uuid4())
    signature = hmac.new(secret.encode(), stamp.encode() + b"\n" + nonce.encode() + b"\n" + body, hashlib.sha256).hexdigest()
    if not valid:
        signature = "0" * 64
    req = urllib.request.Request(gateway.url, data=body, headers={
        "Content-Type": "application/json", "X-G1B2-Key": "synthetic",
        "X-G1B2-Time": stamp, "X-G1B2-Nonce": nonce, "X-G1B2-Signature": signature,
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def runner(path, gateway, secret, *actions):
    env = os.environ.copy()
    env.update(G1B4_URL=gateway.url, G1B4_SECRET=secret, G1B4_D1_PATH=str(path))
    result = subprocess.run(["node", str(HERE / "d1-runner.mjs")], input=json.dumps({"actions": actions}),
                            text=True, capture_output=True, timeout=30, env=env,
                            cwd=HERE.parents[1])
    if result.returncode:
        raise AssertionError(f"D1 runner failed: {result.stderr[-1000:]}")
    output = json.loads(result.stdout)
    for item in output:
        for response in item if isinstance(item, list) else [item]:
            if isinstance(response, dict) and isinstance(response.get("body"), dict) and "wallMs" in response["body"]:
                DISPATCH_WALL_MS.append(response["body"]["wallMs"])
    return output


def broker(action):
    subprocess.run(["docker", action, CONTAINER], check=True, capture_output=True, timeout=30)


def publish_direct(item):
    producer = Producer({"bootstrap.servers": BROKER, "acks": "all", "enable.idempotence": True,
                         "message.timeout.ms": 3000, "error_cb": lambda _error: None, "log_level": 0})
    delivered = []
    producer.produce(TOPIC, key=item["session_id"].encode(),
                     value=json.dumps(item, separators=(",", ":")).encode(),
                     on_delivery=lambda error, message: delivered.append((error, message)))
    producer.flush(5)
    assert len(delivered) == 1 and delivered[0][0] is None
    return delivered[0][1]


def counts(db):
    with sqlite3.connect(db) as conn:
        ack = [x[0] for x in conn.execute("SELECT ack_ms FROM attempts WHERE result='published' AND ack_ms IS NOT NULL")]
        return {
            "receipts": conn.execute("SELECT count(*) FROM receipts").fetchone()[0],
            "published_attempts": conn.execute("SELECT count(*) FROM attempts WHERE result='published'").fetchone()[0],
            "deduplicated_attempts": conn.execute("SELECT count(*) FROM attempts WHERE result='deduplicated'").fetchone()[0],
            "ack_ms_median": round(statistics.median(ack), 3),
            "ack_ms_max": max(ack),
        }


def run():
    admin = AdminClient({"bootstrap.servers": BROKER, "socket.timeout.ms": 3000})
    admin.create_topics([NewTopic(TOPIC, num_partitions=3, replication_factor=1)])[TOPIC].result(10)
    topic = admin.list_topics(TOPIC, timeout=5).topics[TOPIC]
    assert len(topic.partitions) == 3
    secret = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="cogniflow-g1b4-", dir="/tmp") as temp:
        root = Path(temp)
        gateway = KafkaGateway(secret=secret, broker=BROKER, topic=TOPIC,
                               database=root / "gateway.sqlite").start()
        d1 = root / "d1"
        cases = []
        try:
            end_to_end_start = time.monotonic()
            assert runner(d1, gateway, secret, {"type": "init"}, {"type": "append", "event": event(1)}) == [True, True]
            a = runner(d1, gateway, secret, {"type": "dispatch"})[0]
            assert a["http"] == 200 and a["body"]["delivered"] == 1
            first_consumer = DurableConsumer(broker=BROKER, topic=TOPIC, database=root / "consumer.sqlite", group=GROUP)
            try:
                assert first_consumer.consume(max_records=1, timeout=8) == 1
            finally:
                first_consumer.close()
            cold_end_to_end_ms = round((time.monotonic() - end_to_end_start) * 1000, 3)
            cases.append("normal D1-to-Kafka acknowledged delivery")

            item = envelope(event(1))
            nonce = str(uuid.uuid4())
            assert direct(gateway, secret, item, nonce=nonce) == 200
            assert direct(gateway, secret, item, nonce=nonce) == 409
            assert direct(gateway, secret, item, valid=False) == 401
            wrong = envelope({**event(1), "session_kind": "programming"})
            assert direct(gateway, secret, wrong) == 409
            malformed = {**item, "sequence": -1}
            assert direct(gateway, secret, malformed) == 422
            cases.append("duplicate HTTP, nonce replay, invalid HMAC, conflict and malformed payload")

            gateway.faults.put("lost_ack")
            assert runner(d1, gateway, secret, {"type": "append", "event": event(2)},
                          {"type": "dispatch"})[1]["body"]["retried"] == 1
            assert runner(d1, gateway, secret, {"type": "dispatch", "options": {"now": int(time.time()) + 3}})[0]["body"]["delivered"] == 1
            cases.append("lost HTTP acknowledgment and same-ID retry")

            gateway.faults.put("unavailable")
            assert runner(d1, gateway, secret, {"type": "append", "event": event(3)},
                          {"type": "dispatch"})[1]["body"]["retried"] == 1
            assert runner(d1, gateway, secret, {"type": "dispatch", "options": {"now": int(time.time()) + 3}})[0]["body"]["delivered"] == 1
            cases.append("gateway unavailable before publication")

            assert runner(d1, gateway, secret, {"type": "append", "event": event(4)},
                          {"type": "dispatch", "options": {"fault": "crash_after_lease"}})[1]["body"]["claimed"] == 1
            leased = runner(d1, gateway, secret, {"type": "state"})[0]
            old = next(x for x in leased if x["event_id"] == event(4)["event_id"])
            future = int(time.time()) + 11
            assert runner(d1, gateway, secret, {"type": "dispatch", "options": {"now": future}})[0]["body"]["delivered"] == 1
            assert runner(d1, gateway, secret, {"type": "stale_ack", "event_id": event(4)["event_id"],
                          "token": old["lease_token"], "digest": old["digest"], "now": future}) == [False]
            cases.append("dispatcher crash, expired lease recovery and stale acknowledgment fencing")

            assert runner(d1, gateway, secret, {"type": "append", "event": event(5)},
                          {"type": "dispatch", "options": {"fault": "crash_before_mark"}})[1]["body"]["claimed"] == 1
            assert runner(d1, gateway, secret, {"type": "dispatch", "options": {"now": int(time.time()) + 11}})[0]["body"]["delivered"] == 1
            cases.append("dispatcher crash after Kafka acknowledgment and duplicate-safe recovery")

            gateway.close()
            gateway = KafkaGateway(secret=secret, broker=BROKER, topic=TOPIC,
                                   database=root / "gateway.sqlite").start()
            assert direct(gateway, secret, envelope(event(5))) == 200
            cases.append("gateway restart retains durable deduplication")

            gateway.faults.put("reject")
            assert runner(d1, gateway, secret, {"type": "append", "event": event(6)},
                          {"type": "dispatch"})[1]["body"]["dead"] == 1
            cases.append("terminal gateway rejection remains an inspectable dead letter")

            same = "synthetic-g1b4-order"
            runner(d1, gateway, secret, {"type": "append", "event": event(7, session=same)},
                   {"type": "append", "event": event(8, session=same, sequence=2)})
            gateway.faults.put("unavailable")
            assert runner(d1, gateway, secret, {"type": "dispatch"})[0]["body"]["retried"] == 1
            assert runner(d1, gateway, secret, {"type": "dispatch", "options": {"now": int(time.time()) + 3}})[0]["body"]["delivered"] == 1
            assert runner(d1, gateway, secret, {"type": "dispatch"})[0]["body"]["delivered"] == 1
            cases.append("per-session predecessor ordering through a retry")

            consumer = DurableConsumer(broker=BROKER, topic=TOPIC, database=root / "consumer.sqlite", group=GROUP)
            try:
                assert consumer.consume(max_records=1, crash_before_commit=True) == 1
            finally:
                consumer.close()
            consumer = DurableConsumer(broker=BROKER, topic=TOPIC, database=root / "consumer.sqlite", group=GROUP)
            try:
                consumer.consume(max_records=8, timeout=8)
                summary = consumer.counts()
            finally:
                consumer.close()
            assert summary["logical"] >= 7 and summary["duplicates"] >= 1, summary
            cases.append("consumer crash before offset commit, restart, replay and durable logical deduplication")

            concurrent = runner(d1, gateway, secret, {"type": "append", "event": event(10)},
                                {"type": "concurrent"})[1]
            assert sum(x["body"]["delivered"] for x in concurrent) == 1
            assert all(x["http"] == 200 for x in concurrent)
            cases.append("concurrent dispatchers claim one D1 lease")

            broker("stop")
            try:
                assert runner(d1, gateway, secret, {"type": "append", "event": event(9)},
                              {"type": "dispatch"})[1]["body"]["retried"] == 1
            finally:
                broker("start")
            for _ in range(15):
                try:
                    admin.list_topics(TOPIC, timeout=2)
                    break
                except Exception:
                    time.sleep(1)
            assert runner(d1, gateway, secret, {"type": "dispatch", "options": {"now": int(time.time()) + 3}})[0]["body"]["delivered"] == 1
            cases.append("actual broker outage, restart, retry and durable topic recovery")

            consumer = DurableConsumer(broker=BROKER, topic=TOPIC, database=root / "consumer.sqlite", group=GROUP)
            try:
                assert consumer.consume(max_records=2, timeout=8) == 2
                summary = consumer.counts()
            finally:
                consumer.close()
            assert summary["logical"] == 9, summary

            publish_direct(envelope(event(1)))
            publish_direct(envelope({**event(1), "session_kind": "programming"}))
            consumer = DurableConsumer(broker=BROKER, topic=TOPIC, database=root / "consumer.sqlite", group=GROUP)
            try:
                assert consumer.consume(max_records=1, timeout=8) == 1
                try:
                    consumer.consume(max_records=1, timeout=8)
                except ValueError as error:
                    assert "conflicting Kafka event ID" in str(error)
                else:
                    raise AssertionError("consumer accepted conflicting event ID")
                summary = consumer.counts()
            finally:
                consumer.close()
            assert summary["logical"] == 9 and summary["duplicates"] >= 2
            cases.append("duplicate Kafka record, durable consumer deduplication and conflicting-ID rejection")

            states = runner(d1, gateway, secret, {"type": "state"})[0]
            assert sum(x["state"] == "dead" for x in states) == 1
            receipts = counts(root / "gateway.sqlite")
            assert receipts["receipts"] == sum(x["state"] == "acknowledged" for x in states)
            assert receipts["deduplicated_attempts"] >= 2
            assert summary["logical"] == receipts["receipts"]
            with sqlite3.connect(root / "gateway.sqlite") as conn:
                receipt_ids = [x[0] for x in conn.execute("SELECT event_id FROM receipts")]
                attempts = [x[0] for x in conn.execute("SELECT event_id FROM attempts")]
                order = conn.execute("SELECT event_id,partition_id,offset_id FROM receipts WHERE event_id IN (?,?) ORDER BY offset_id",
                                     (event(7)["event_id"], event(8)["event_id"])).fetchall()
            with sqlite3.connect(root / "consumer.sqlite") as conn:
                processed_ids = [x[0] for x in conn.execute("SELECT event_id FROM processed")]
            expected_ids = [x["event_id"] for x in states if x["state"] == "acknowledged"]
            reconciliation = reconcile(expected_ids, receipt_ids, processed_ids, attempts)
            assert not any(reconciliation[key] for key in ("missing_receipts", "missing_processed",
                                                  "unexpected_receipts", "unexpected_processed"))
            assert len(reconciliation["duplicate_attempt_ids"]) >= 2
            assert len(order) == 2 and order[0][0] == event(7)["event_id"] and order[1][0] == event(8)["event_id"] and order[0][1] == order[1][1]
            cases.append("reconciliation of D1, Kafka receipts and consumer; same-partition session order")
            print(json.dumps({"cases": cases, "gateway": receipts, "consumer": summary,
                              "reconciliation": reconciliation,
                              "cold_append_to_durable_consume_ms": cold_end_to_end_ms,
                              "dispatcher_wall_ms_median": round(statistics.median(DISPATCH_WALL_MS), 3),
                              "dispatcher_wall_ms_max": round(max(DISPATCH_WALL_MS), 3),
                              "outbox_states": {x["event_id"]: x["state"] for x in states},
                              "topic_partitions": len(topic.partitions)}, indent=2))
        finally:
            gateway.close()


if __name__ == "__main__":
    run()
