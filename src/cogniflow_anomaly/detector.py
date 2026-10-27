"""Persistent, bounded sliding-window detector for sanitized activity events."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from cogniflow_eventing.consumer import parse_delivery
from preprocessing_api.activity_events import MAX_EVENT_BYTES

ALERT_TYPE = "org.cogniflow.inference.anomaly.v1"
ALERT_SOURCE = "urn:cogniflow:anomaly-detector"
ALERT_SCHEMA_VERSION = "1.0"
MAX_STATE_EVENTS = 10_000
MAX_ALERTS = 10_000
MAX_OUTBOX_BACKLOG = 10_000
MAX_DEDUP_EVENTS = 100_000
OUTBOX_BATCH_SIZE = 4
RETENTION_SECONDS = 3_600
DEDUP_RETENTION_SECONDS = 7 * 24 * 3_600
LATENESS_SECONDS = 10
OUTBOX_RETRY_MIN_SECONDS = 0.25
OUTBOX_RETRY_MAX_SECONDS = 30.0
OUTBOX_IDLE_SECONDS = 1.0
MAX_CONCURRENT_REQUESTS = 8

_database_lock = threading.RLock()


@dataclass(frozen=True)
class Rule:
    id: str
    version: str
    window_seconds: int
    minimum_samples: int
    threshold: float
    operator: str
    metric: str
    severity: str
    cooldown_seconds: int


DEFAULT_RULES = (
    Rule("inference_error_ratio", "1.0", 60, 4, 0.5, ">=", "error_ratio", "high", 60),
    Rule("inference_mean_latency_ms", "1.0", 60, 3, 500.0, ">=", "mean_latency_ms", "medium", 60),
    Rule("inference_request_count", "1.0", 60, 6, 5.0, ">", "request_count", "medium", 60),
)

EVENTS = Counter("cogniflow_anomaly_events_total", "Detector event outcomes.", ["result"])
ALERTS = Counter("cogniflow_anomaly_alerts_total", "Detector alert outcomes.", ["result", "rule"])
ACTIVE_WINDOWS = Gauge("cogniflow_anomaly_active_windows", "Active rule windows.")
OUTBOX_BACKLOG = Gauge("cogniflow_anomaly_outbox_backlog", "Unpublished anomaly alerts.")
DETECTION_LATENCY = Histogram(
    "cogniflow_anomaly_detection_latency_seconds", "Activity event time to alert decision."
)

class OutboxFullError(RuntimeError):
    """The durable publication backlog has reached its explicit limit."""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    wake = asyncio.Event()
    app.state.outbox_wake = wake
    app.state.request_slots = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    task = asyncio.create_task(_outbox_worker(stop, wake))
    try:
        yield
    finally:
        stop.set()
        wake.set()
        await task


app = FastAPI(title="CogniFlow anomaly detector", docs_url=None, redoc_url=None, lifespan=lifespan)


def configured_rules() -> tuple[Rule, ...]:
    version = os.getenv("ANOMALY_RULE_VERSION", "1.0")
    if not version or len(version) > 32:
        raise ValueError("invalid anomaly rule version")
    rules = []
    for rule in DEFAULT_RULES:
        prefix = rule.id.upper()
        window = int(os.getenv(f"{prefix}_WINDOW_SECONDS", str(rule.window_seconds)))
        minimum = int(os.getenv(f"{prefix}_MINIMUM_SAMPLES", str(rule.minimum_samples)))
        threshold = float(os.getenv(f"{prefix}_THRESHOLD", str(rule.threshold)))
        cooldown = int(os.getenv(f"{prefix}_COOLDOWN_SECONDS", str(rule.cooldown_seconds)))
        if not 1 <= window <= RETENTION_SECONDS or not 1 <= minimum <= MAX_STATE_EVENTS:
            raise ValueError("invalid anomaly window configuration")
        if not math.isfinite(threshold) or threshold < 0 or not 0 <= cooldown <= RETENTION_SECONDS:
            raise ValueError("invalid anomaly threshold configuration")
        rules.append(Rule(rule.id, version, window, minimum, threshold, rule.operator, rule.metric, rule.severity, cooldown))
    return tuple(rules)


def _path() -> Path:
    return Path(os.getenv("ANOMALY_STORE_PATH", "/data/anomalies.sqlite3"))


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
              source TEXT NOT NULL, id TEXT NOT NULL, event_time TEXT NOT NULL,
              backend TEXT NOT NULL, failed INTEGER NOT NULL, latency_ms REAL NOT NULL,
              PRIMARY KEY (source, id));
            CREATE INDEX IF NOT EXISTS events_window ON events(backend, event_time);
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS deliveries (
              source TEXT NOT NULL, id TEXT NOT NULL, seen_at TEXT NOT NULL,
              PRIMARY KEY (source, id));
            CREATE INDEX IF NOT EXISTS deliveries_retention ON deliveries(seen_at);
            INSERT OR IGNORE INTO deliveries
              SELECT source, id, datetime('now') FROM events
              WHERE NOT EXISTS (SELECT 1 FROM metadata WHERE key='dedup_migrated');
            INSERT OR IGNORE INTO metadata VALUES ('dedup_migrated', '1');
            CREATE TABLE IF NOT EXISTS alerts (
              id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, rule_version TEXT NOT NULL, backend TEXT NOT NULL,
              detected_at TEXT NOT NULL, event_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox (
              id TEXT PRIMARY KEY REFERENCES alerts(id), event_json TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0, published_at TEXT);
            """
        )
        with connection:
            yield connection
    finally:
        connection.close()


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be UTC")
    return parsed.astimezone(UTC)


def _measured(rule: Rule, rows: list[sqlite3.Row]) -> float:
    if rule.metric == "error_ratio":
        return sum(row["failed"] for row in rows) / len(rows)
    if rule.metric == "mean_latency_ms":
        return sum(row["latency_ms"] for row in rows) / len(rows)
    return float(len(rows))


def _triggered(rule: Rule, measured: float) -> bool:
    return measured >= rule.threshold if rule.operator == ">=" else measured > rule.threshold


def _alert(rule: Rule, event: dict[str, Any], start: datetime, end: datetime, measured: float, count: int) -> dict[str, Any]:
    backend = event["data"]["inference_backend"]
    identity = f"{rule.id}:{rule.version}:{backend}:{event['id']}"
    anomaly_id = hashlib.sha256(identity.encode()).hexdigest()
    return {
        "specversion": "1.0",
        "id": anomaly_id,
        "source": ALERT_SOURCE,
        "type": ALERT_TYPE,
        "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "datacontenttype": "application/json",
        "data": {
            "schema_version": ALERT_SCHEMA_VERSION,
            "anomaly_id": anomaly_id,
            "rule_id": rule.id,
            "rule_version": rule.version,
            "detected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "window_start": start.isoformat().replace("+00:00", "Z"),
            "window_end": end.isoformat().replace("+00:00", "Z"),
            "backend": backend,
            "observed_metric": measured,
            "threshold": rule.threshold,
            "operator": rule.operator,
            "sample_count": count,
            "severity": rule.severity,
            "triggering_event_id": event["id"],
            "provenance": "synthetic_demo",
        },
    }


def process_event(event: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    event_time = _utc(event["time"])
    backend = event["data"]["inference_backend"]
    generated: list[dict[str, Any]] = []
    with _database_lock, _connect() as connection:
        duplicate = connection.execute(
            "SELECT 1 FROM deliveries WHERE source=? AND id=?", (event["source"], event["id"])
        ).fetchone()
        if duplicate:
            EVENTS.labels("duplicate").inc()
            return "duplicate", []
        backlog = connection.execute(
            "SELECT count(*) FROM outbox WHERE published_at IS NULL"
        ).fetchone()[0]
        if backlog >= MAX_OUTBOX_BACKLOG:
            raise OutboxFullError("outbox backlog limit reached")
        now = datetime.now(UTC)
        connection.execute(
            "DELETE FROM deliveries WHERE seen_at < ?",
            ((now - timedelta(seconds=DEDUP_RETENTION_SECONDS)).isoformat(),),
        )
        excess = connection.execute("SELECT count(*) - ? FROM deliveries", (MAX_DEDUP_EVENTS - 1,)).fetchone()[0]
        if excess > 0:
            connection.execute(
                "DELETE FROM deliveries WHERE rowid IN (SELECT rowid FROM deliveries ORDER BY seen_at LIMIT ?)",
                (excess,),
            )
        connection.execute(
            "INSERT INTO deliveries VALUES (?, ?, ?)", (event["source"], event["id"], now.isoformat())
        )
        previous = connection.execute("SELECT value FROM metadata WHERE key='max_event_time'").fetchone()
        maximum = _utc(previous[0]) if previous else event_time
        if event_time < maximum - timedelta(seconds=LATENESS_SECONDS):
            EVENTS.labels("late").inc()
            return "late", []
        maximum = max(maximum, event_time)
        connection.execute(
            "INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?)",
            (event["source"], event["id"], event_time.isoformat(), backend,
             int(event["data"]["outcome"] == "failure"), float(event["data"]["latency_ms"])),
        )
        connection.execute(
            "INSERT INTO metadata VALUES ('max_event_time', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (maximum.isoformat(),),
        )
        connection.execute("DELETE FROM events WHERE event_time < ?", ((maximum - timedelta(seconds=RETENTION_SECONDS)).isoformat(),))
        excess = connection.execute("SELECT count(*) - ? FROM events", (MAX_STATE_EVENTS,)).fetchone()[0]
        if excess > 0:
            connection.execute("DELETE FROM events WHERE rowid IN (SELECT rowid FROM events ORDER BY event_time LIMIT ?)", (excess,))
        rules = configured_rules()
        for rule in rules:
            start = event_time - timedelta(seconds=rule.window_seconds)
            rows = connection.execute(
                "SELECT failed, latency_ms FROM events WHERE backend=? AND event_time>? AND event_time<=? ORDER BY event_time",
                (backend, start.isoformat(), event_time.isoformat()),
            ).fetchall()
            if len(rows) < rule.minimum_samples:
                continue
            measured = _measured(rule, rows)
            if not _triggered(rule, measured):
                continue
            recent = connection.execute(
                "SELECT detected_at FROM alerts WHERE rule_id=? AND rule_version=? AND backend=? ORDER BY detected_at DESC LIMIT 1",
                (rule.id, rule.version, backend),
            ).fetchone()
            if recent and event_time < _utc(recent[0]) + timedelta(seconds=rule.cooldown_seconds):
                ALERTS.labels("suppressed", rule.id).inc()
                continue
            alert = _alert(rule, event, start, event_time, measured, len(rows))
            serialized = json.dumps(alert, separators=(",", ":"), sort_keys=True)
            connection.execute(
                "INSERT OR IGNORE INTO alerts VALUES (?, ?, ?, ?, ?, ?)",
                (alert["id"], rule.id, rule.version, backend, event_time.isoformat(), serialized),
            )
            connection.execute("INSERT OR IGNORE INTO outbox(id, event_json) VALUES (?, ?)", (alert["id"], serialized))
            generated.append(alert)
            ALERTS.labels("generated", rule.id).inc()
    EVENTS.labels("processed").inc()
    ACTIVE_WINDOWS.set(len(rules))
    DETECTION_LATENCY.observe(max(0.0, (datetime.now(UTC) - event_time).total_seconds()))
    return "processed", generated


def _destination() -> str:
    value = os.environ["ANOMALY_ALERT_DESTINATION"]
    parsed = urllib.parse.urlsplit(value)
    host = parsed.hostname or ""
    if parsed.scheme != "http" or not (host in {"localhost", "127.0.0.1"} or host.endswith(".svc") or host.endswith(".svc.cluster.local")):
        raise ValueError("alert destination must be internal HTTP")
    if parsed.username or parsed.query or parsed.fragment:
        raise ValueError("invalid alert destination")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def flush_outbox() -> bool:
    destination = _destination()
    with _database_lock, _connect() as connection:
        pending = connection.execute(
            "SELECT id, event_json FROM outbox WHERE published_at IS NULL ORDER BY rowid LIMIT ?",
            (OUTBOX_BATCH_SIZE,),
        ).fetchall()
    OUTBOX_BACKLOG.set(len(pending))
    for row in pending:
        request = urllib.request.Request(destination, data=row["event_json"].encode(), headers={"Content-Type": "application/cloudevents+json"}, method="POST")
        try:
            opener = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=2) as response:
                if not 200 <= response.status < 300:
                    raise OSError("alert sink rejected event")
        except (OSError, urllib.error.URLError):
            with _database_lock, _connect() as connection:
                connection.execute("UPDATE outbox SET attempts=attempts+1 WHERE id=?", (row["id"],))
            ALERTS.labels("publication_failed", "all").inc()
            return False
        with _database_lock, _connect() as connection:
            connection.execute("UPDATE outbox SET published_at=? WHERE id=?", (datetime.now(UTC).isoformat(), row["id"]))
    with _database_lock, _connect() as connection:
        remaining = connection.execute("SELECT count(*) FROM outbox WHERE published_at IS NULL").fetchone()[0]
        excess = connection.execute("SELECT count(*) - ? FROM alerts", (MAX_ALERTS,)).fetchone()[0]
        if excess > 0:
            removable = connection.execute(
                "SELECT alerts.id FROM alerts JOIN outbox USING(id) WHERE published_at IS NOT NULL ORDER BY alerts.rowid LIMIT ?",
                (excess,),
            ).fetchall()
            connection.executemany("DELETE FROM outbox WHERE id=?", removable)
            connection.executemany("DELETE FROM alerts WHERE id=?", removable)
    OUTBOX_BACKLOG.set(remaining)
    return remaining == 0


async def _outbox_worker(stop: asyncio.Event, wake: asyncio.Event) -> None:
    delay = OUTBOX_RETRY_MIN_SECONDS
    while not stop.is_set():
        previous = 0
        try:
            previous = await asyncio.to_thread(_outbox_count)
            drained = await asyncio.to_thread(flush_outbox)
            remaining = await asyncio.to_thread(_outbox_count)
        except (KeyError, ValueError, sqlite3.Error):
            drained = False
            remaining = previous
        timeout = OUTBOX_IDLE_SECONDS if drained else delay
        delay = (
            OUTBOX_RETRY_MIN_SECONDS
            if drained or remaining < previous
            else min(delay * 2, OUTBOX_RETRY_MAX_SECONDS)
        )
        try:
            await asyncio.wait_for(wake.wait(), timeout=timeout)
            wake.clear()
        except TimeoutError:
            pass


def _outbox_count() -> int:
    with _database_lock, _connect() as connection:
        return connection.execute(
            "SELECT count(*) FROM outbox WHERE published_at IS NULL"
        ).fetchone()[0]


async def _process_event(event: dict[str, Any]) -> None:
    task = asyncio.create_task(asyncio.to_thread(process_event, event))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    try:
        configured_rules()
        _destination()
        with _database_lock, _connect() as connection:
            connection.execute("SELECT 1")
    except (KeyError, ValueError, sqlite3.Error) as exc:
        raise HTTPException(503, "detector store unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/")
async def consume(request: Request) -> Response:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_EVENT_BYTES:
            EVENTS.labels("invalid").inc()
            raise HTTPException(413, "event too large")
        body.extend(chunk)
    try:
        event = parse_delivery(bytes(body), request.headers)
    except (ValueError, TypeError, json.JSONDecodeError):
        EVENTS.labels("invalid").inc()
        raise HTTPException(400, "invalid activity event") from None
    slots = getattr(request.app.state, "request_slots", None)
    if slots is None:
        slots = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    try:
        async with slots:
            await _process_event(event)
    except OutboxFullError:
        EVENTS.labels("overloaded").inc()
        raise HTTPException(503, "durable alert backlog full") from None
    except (ValueError, sqlite3.Error):
        EVENTS.labels("failed").inc()
        raise HTTPException(503, "anomaly detector unavailable") from None
    wake = getattr(request.app.state, "outbox_wake", None)
    if wake is not None:
        wake.set()
    return Response(status_code=204)
