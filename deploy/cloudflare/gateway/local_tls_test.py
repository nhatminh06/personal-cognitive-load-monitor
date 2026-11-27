"""Disposable synthetic D1 → verified HTTPS → real Kafka → durable consumer test."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import resource
import secrets
import sqlite3
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka import Producer
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from kafka_gateway import KafkaGateway

HERE = Path(__file__).resolve().parent
BROKER = "127.0.0.1:39095"


def certificates(root: Path):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "G1D2 disposable CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (x509.CertificateBuilder().subject_name(server_name).issuer_name(ca_name)
            .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    ca_path, cert_path, key_path = (root / name for name in ("ca.pem", "server.pem", "server.key"))
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(server_key.private_bytes(serialization.Encoding.PEM,
                                                 serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()))
    key_path.chmod(0o600)
    return ca_path, cert_path, key_path


def event(number):
    stamp = "2026-11-26T00:00:00+00:00"
    return {"schema_version": "1.0", "event_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"g1d2:{number}")),
            "idempotency_key": f"g1d2-{number}", "session_id": f"synthetic-g1d2-{number}",
            "subject_id": None, "source": "synthetic", "producer_version": "g1d2",
            "event_type": "session.started", "sequence": 1, "session_kind": "study",
            "privacy_mode": "behavioral", "event_time": stamp, "ingested_at": stamp}


def envelope(ev):
    payload = json.dumps(ev, separators=(",", ":"))
    return {"event_id": ev["event_id"], "session_id": ev["session_id"], "sequence": 1,
            "digest": hashlib.sha256(payload.encode()).hexdigest(), "payload": payload}


def request(url, ca, key, secret, item, *, nonce=None, stamp=None, signature=None, body=None):
    raw = body if body is not None else json.dumps(item, separators=(",", ":")).encode()
    nonce, stamp = nonce or str(uuid.uuid4()), stamp or str(int(time.time()))
    signature = signature or hmac.new(secret.encode(), stamp.encode() + b"\n" + nonce.encode() + b"\n" + raw,
                                      hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, data=raw, headers={"Content-Type": "application/json",
        "X-G1B2-Key": key, "X-G1B2-Time": stamp, "X-G1B2-Nonce": nonce, "X-G1B2-Signature": signature})
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(cafile=str(ca)), timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def runner(root, ca, gateway, secret, key, actions):
    env = {**os.environ, "G1D2_D1_PATH": str(root / "d1"), "G1D2_URL": gateway.url,
           "G1D2_SECRET": secret, "G1D2_KEY_ID": key, "NODE_EXTRA_CA_CERTS": str(ca)}
    result = subprocess.run(["node", str(HERE / "tls_dispatch.mjs")], input=json.dumps(actions),
                            text=True, capture_output=True, timeout=30, env=env, cwd=HERE.parent)
    if result.returncode:
        raise AssertionError(result.stderr[-1200:])
    return json.loads(result.stdout)


def run():
    topic = f"g1b4-g1d2-{os.getpid()}"
    group = f"g1b4-g1d2-{os.getpid()}"
    admin = AdminClient({"bootstrap.servers": BROKER})
    admin.create_topics(
        [NewTopic(topic, num_partitions=2, replication_factor=1)])[topic].result(10)
    with tempfile.TemporaryDirectory(prefix="cogniflow-g1d2-", dir="/tmp") as temp:
        root = Path(temp)
        ca, cert, key_path = certificates(root)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert, key_path)
        old, new = secrets.token_hex(32), secrets.token_hex(32)
        gateway = KafkaGateway(secret=old, secrets={"old": old, "new": new},
                               broker=BROKER, topic=topic, database=root / "gateway.sqlite",
                               tls_context=context).start()
        try:
            ev = event(1)
            result = runner(root, ca, gateway, old, "old", [{"type": "init"}, {"type": "append", "event": ev},
                                                          {"type": "dispatch"}, {"type": "state"}])
            assert result[2]["delivered"] == 1 and result[3][0]["state"] == "acknowledged", result
            item = envelope(ev)
            nonce = str(uuid.uuid4())
            assert request(gateway.url, ca, "old", old, item, nonce=nonce) == 200
            assert request(gateway.url, ca, "old", old, item, nonce=nonce) == 409
            assert request(gateway.url, ca, "old", old, item, signature="0" * 64) == 401
            assert request(gateway.url, ca, "old", old, item, stamp=str(int(time.time()) - 60)) == 401
            assert request(gateway.url, ca, "old", old, {**item, "sequence": -1}) == 422
            assert request(gateway.url, ca, "old", old, {**item, "payload": "x" * 9000}) == 413
            unsupported = envelope({**event(2), "event_type": "unknown"})
            assert request(gateway.url, ca, "old", old, unsupported) == 422
            assert request(gateway.url, ca, "new", new, item) == 200
            assert request(gateway.url, ca, "old", new, item) == 401
            replica = KafkaGateway(secret=old, secrets={"old": old, "new": new}, broker=BROKER,
                                   topic=topic, database=root / "gateway.sqlite", tls_context=context).start()
            try:
                assert request(replica.url, ca, "old", old, item, nonce=nonce) == 409
                assert request(replica.url, ca, "new", new, item) == 200
            finally:
                replica.close()
            gateway.faults.put("lost_ack")
            replay = runner(root, ca, gateway, old, "old", [{"type": "append", "event": event(2)},
                {"type": "dispatch"}, {"type": "dispatch", "options": {"now": int(time.time()) + 3}}])
            assert replay[1]["retried"] == 1 and replay[2]["delivered"] == 1, replay
            gateway.faults.put("unavailable")
            retry = runner(root, ca, gateway, old, "old", [{"type": "append", "event": event(3)},
                {"type": "dispatch"}, {"type": "dispatch", "options": {"now": int(time.time()) + 3}}])
            assert retry[1]["retried"] == 1 and retry[2]["delivered"] == 1, retry
            concurrent = runner(root, ca, gateway, old, "old", [{"type": "append", "event": event(4)},
                                                           {"type": "concurrent"}])[1]
            assert sum(x["delivered"] for x in concurrent) == 1, concurrent
            gateway.faults.put("reject")
            dead = runner(root, ca, gateway, old, "old", [{"type": "append", "event": event(5)},
                                                     {"type": "dispatch"}, {"type": "state"}])
            assert dead[1]["dead"] == 1 and dead[2][-1]["state"] == "dead", dead
            if os.environ.get("G1D2_TEST_BROKER_RESTART") == "1":
                container = "cogniflow-g1d2-kafka-20261127"
                subprocess.run(["docker", "stop", container], check=True, capture_output=True, timeout=30)
                try:
                    outage = runner(root, ca, gateway, old, "old", [{"type": "append", "event": event(6)},
                                                                 {"type": "dispatch"}])
                    assert outage[1]["retried"] == 1, outage
                finally:
                    subprocess.run(["docker", "start", container], check=True, capture_output=True, timeout=30)
                admin = AdminClient({"bootstrap.servers": BROKER, "socket.timeout.ms": 2000})
                for _ in range(15):
                    try:
                        admin.list_topics(topic, timeout=2)
                        break
                    except Exception:
                        time.sleep(1)
                else:
                    raise AssertionError("broker did not recover")
                recovered = runner(root, ca, gateway, old, "old", [{"type": "dispatch",
                    "options": {"now": int(time.time()) + 4}}])[0]
                assert recovered["delivered"] == 1, recovered
            try:
                urllib.request.urlopen(gateway.url, timeout=2)
            except (ssl.SSLCertVerificationError, urllib.error.URLError):
                pass
            else:
                raise AssertionError("untrusted CA accepted")
            try:
                urllib.request.urlopen(gateway.url.replace("localhost", "127.0.0.1"),
                                       context=ssl.create_default_context(cafile=str(ca)), timeout=2)
            except (ssl.SSLCertVerificationError, urllib.error.URLError):
                pass
            else:
                raise AssertionError("wrong hostname accepted")
            wall_samples = gateway.request_wall_ms.copy()
            cpu_samples = gateway.request_thread_cpu_ms.copy()
            gateway.close()
            gateway = KafkaGateway(secret=old, secrets={"new": new}, broker=BROKER,
                                   topic=topic, database=root / "gateway.sqlite", tls_context=context).start()
            assert request(gateway.url, ca, "new", new, item, nonce=nonce) == 409
            assert request(gateway.url, ca, "old", old, item) == 401
            assert request(gateway.url, ca, "new", new, item) == 200
            from sys import path
            path.insert(0, str(HERE.parent / "prototypes" / "g1b4-kafka"))
            from consumer import DurableConsumer
            consumer = DurableConsumer(broker=BROKER, topic=topic, database=root / "consumer.sqlite", group=group)
            try:
                expected = 5 if os.environ.get("G1D2_TEST_BROKER_RESTART") == "1" else 4
                assert consumer.consume(max_records=expected, timeout=10) == expected
                summary = consumer.counts()
                assert summary["logical"] == expected
            finally:
                consumer.close()
            producer = Producer({"bootstrap.servers": BROKER, "acks": "all",
                                 "message.timeout.ms": 3000, "log_level": 0})
            producer.produce(topic, key=ev["session_id"].encode(),
                             value=json.dumps(item, separators=(",", ":")).encode())
            assert producer.flush(5) == 0
            consumer = DurableConsumer(broker=BROKER, topic=topic, database=root / "consumer.sqlite", group=group)
            try:
                assert consumer.consume(max_records=1, timeout=10) == 1
                assert consumer.counts()["logical"] == expected
                assert consumer.counts()["duplicates"] == 1
                summary = consumer.counts()
            finally:
                consumer.close()
            with sqlite3.connect(root / "gateway.sqlite") as db:
                assert db.execute("SELECT count(*) FROM receipts").fetchone()[0] == expected
                assert db.execute("SELECT count(*) FROM nonces").fetchone()[0] >= 3
                ack = [row[0] for row in db.execute("SELECT ack_ms FROM attempts WHERE ack_ms IS NOT NULL")]
                attempts = db.execute("SELECT result,count(*) FROM attempts GROUP BY result").fetchall()
            wall_samples.extend(gateway.request_wall_ms)
            cpu_samples.extend(gateway.request_thread_cpu_ms)
            print(json.dumps({"tls": "verified", "dispatch": result[2], "consumer": summary,
                              "gateway_requests": len(wall_samples),
                              "gateway_wall_ms_max": round(max(wall_samples), 3),
                              "gateway_thread_cpu_ms_max": round(max(cpu_samples), 3),
                              "gateway_process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                              "kafka_ack_ms_max": max(ack), "gateway_attempts": dict(attempts)}))
        finally:
            gateway.close()


if __name__ == "__main__":
    run()
