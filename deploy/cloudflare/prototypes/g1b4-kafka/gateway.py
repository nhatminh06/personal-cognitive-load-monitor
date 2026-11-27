"""Loopback-only synthetic G1B.4 gateway. Never expose this server publicly."""

from __future__ import annotations

import hashlib
import hmac
import json
import queue
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from confluent_kafka import KafkaException, Producer


class KafkaGateway:
    def __init__(self, *, secret: str, broker: str, topic: str, database: Path,
                 max_requests: int = 200, behavioral_topic: str | None = None):
        if not secret or not broker.startswith("127.0.0.1:") or not topic.startswith("g1b4-"):
            raise ValueError("unsafe gateway configuration")
        if not 1 <= max_requests <= 1000:
            raise ValueError("unsafe request cap")
        if behavioral_topic not in (None, "cogniflow.behavioral-activity.v1"):
            raise ValueError("unsupported behavioral topic")
        self.secret, self.topic = secret.encode(), topic
        self.behavioral_topic = behavioral_topic
        self.requests, self.max_requests = 0, max_requests
        self.database = Path(database)
        self.faults: queue.Queue[str] = queue.Queue(maxsize=16)
        self.lock = threading.Lock()
        self.producer = Producer({
            "bootstrap.servers": broker,
            "acks": "all",
            "enable.idempotence": True,
            "retries": 2,
            "message.timeout.ms": 3000,
            "socket.timeout.ms": 2000,
            "queue.buffering.max.messages": 100,
            "log_level": 0,
            "error_cb": lambda _error: None,
        })
        with closing(self._db()) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (
                  event_id TEXT PRIMARY KEY, digest TEXT NOT NULL, session_id TEXT NOT NULL,
                  partition_id INTEGER NOT NULL, offset_id INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                  id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, result TEXT NOT NULL,
                  ack_ms REAL);
            """)
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                gateway._handle(self)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def _db(self):
        db = sqlite3.connect(self.database, timeout=2)
        db.execute("PRAGMA busy_timeout=2000")
        return db

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}/ingest"

    def start(self):
        self.thread.start()
        return self

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.producer.flush(3)

    @staticmethod
    def _reply(handler, code, body=None):
        raw = json.dumps(body or {}, separators=(",", ":")).encode()
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        try:
            handler.wfile.write(raw)
        except BrokenPipeError:
            pass

    def _handle(self, handler):
        with self.lock:
            self.requests += 1
            if self.requests > self.max_requests:
                return self._reply(handler, 429)
        if handler.path != "/ingest" or handler.headers.get("Content-Type") != "application/json":
            return self._reply(handler, 404)
        try:
            length = int(handler.headers.get("Content-Length", "-1"))
            if length < 1 or length > 8192:
                return self._reply(handler, 413)
            body = handler.rfile.read(length)
            stamp = handler.headers.get("X-G1B2-Time", "")
            nonce = handler.headers.get("X-G1B2-Nonce", "")
            signature = handler.headers.get("X-G1B2-Signature", "")
            if handler.headers.get("X-G1B2-Key") != "synthetic" or not stamp.isascii() or not stamp.isdigit() or len(stamp) > 12:
                return self._reply(handler, 401)
            if abs(int(stamp) - int(time.time())) > 30:
                return self._reply(handler, 401)
            try:
                uuid.UUID(nonce)
                supplied = bytes.fromhex(signature)
            except ValueError:
                return self._reply(handler, 401)
            expected = hmac.new(self.secret, stamp.encode() + b"\n" + nonce.encode() + b"\n" + body, hashlib.sha256).digest()
            if len(supplied) != 32 or not hmac.compare_digest(supplied, expected):
                return self._reply(handler, 401)
            item = json.loads(body)
            if not isinstance(item, dict) or set(item) != {"event_id", "session_id", "sequence", "digest", "payload"}:
                return self._reply(handler, 422)
            uuid.UUID(item["event_id"])
            if not isinstance(item["session_id"], str) or not (1 <= len(item["session_id"]) <= 128) or not all(c.isalnum() or c in "._:-" for c in item["session_id"]):
                return self._reply(handler, 422)
            if type(item["sequence"]) is not int or not (0 <= item["sequence"] <= 2147483647) or not isinstance(item["payload"], str) or len(item["payload"].encode()) > 4096:
                return self._reply(handler, 422)
            digest = hashlib.sha256(item["payload"].encode()).hexdigest()
            if not isinstance(item["digest"], str) or not hmac.compare_digest(digest, item["digest"]):
                return self._reply(handler, 422)
            event = json.loads(item["payload"])
            if not isinstance(event, dict) or event.get("schema_version") != "1.0" or event.get("event_id") != item["event_id"] or event.get("session_id") != item["session_id"] or event.get("sequence", 0) != item["sequence"]:
                return self._reply(handler, 422)
            if event.get("source") != "synthetic" or event.get("subject_id") is not None:
                return self._reply(handler, 422)
            lifecycle = event.get("event_type") in {"session.started", "session.paused", "session.resumed", "session.completed", "session.cancelled"}
            if lifecycle and item["sequence"] < 1 or not lifecycle and (event.get("event_type") not in {"behavioral.window", "effort.reported"} or item["sequence"] != 0):
                return self._reply(handler, 422)
            target_topic, kafka_value = self.topic, body
            if self.behavioral_topic:
                from cogniflow_contracts import (BehavioralActivityEvent, EffortLabelEvent,
                                                  SessionLifecycleEvent)
                from pydantic import ValidationError

                try:
                    if lifecycle:
                        SessionLifecycleEvent.model_validate(event)
                    elif event["event_type"] == "effort.reported":
                        EffortLabelEvent.model_validate(event)
                    else:
                        BehavioralActivityEvent.model_validate(event)
                except ValidationError:
                    return self._reply(handler, 422)
                if event["event_type"] == "behavioral.window":
                    target_topic, kafka_value = self.behavioral_topic, item["payload"].encode()
            with self.lock, closing(self._db()) as db, db:
                try:
                    db.execute("INSERT INTO nonces VALUES (?,?)", (nonce, int(stamp) + 30))
                except sqlite3.IntegrityError:
                    return self._reply(handler, 409)
                previous = db.execute("SELECT digest FROM receipts WHERE event_id=?", (item["event_id"],)).fetchone()
                if previous:
                    if not hmac.compare_digest(previous[0], digest):
                        return self._reply(handler, 409)
                    db.execute("INSERT INTO attempts(event_id,result) VALUES (?,?)", (item["event_id"], "deduplicated"))
                    db.commit()
                    return self._reply(handler, 200, {"event_id": item["event_id"], "digest": digest})
                fault = self.faults.get_nowait() if not self.faults.empty() else "ok"
                if fault == "reject":
                    return self._reply(handler, 403)
                if fault == "unavailable":
                    return self._reply(handler, 503)
                result = []
                sent_at = time.monotonic()
                try:
                    self.producer.produce(target_topic, key=item["session_id"].encode(), value=kafka_value,
                                          on_delivery=lambda error, msg: result.append((error, msg)))
                    deadline = time.monotonic() + 3
                    while not result and time.monotonic() < deadline:
                        self.producer.poll(min(0.1, deadline - time.monotonic()))
                except (BufferError, KafkaException):
                    return self._reply(handler, 503)
                if not result:
                    return self._reply(handler, 504)
                error, message = result[0]
                if error:
                    return self._reply(handler, 504 if error.retriable() else 503)
                db.execute("INSERT INTO receipts VALUES (?,?,?,?,?)", (item["event_id"], digest,
                           item["session_id"], message.partition(), message.offset()))
                db.execute("INSERT INTO attempts(event_id,result,ack_ms) VALUES (?,?,?)",
                           (item["event_id"], "published", round((time.monotonic() - sent_at) * 1000, 3)))
                db.commit()
                if fault == "lost_ack":
                    return self._reply(handler, 504)
                return self._reply(handler, 200, {"event_id": item["event_id"], "digest": digest})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
            return self._reply(handler, 422)
        except Exception:
            return self._reply(handler, 503)
