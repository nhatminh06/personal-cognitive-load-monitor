"""Persistent internal sink for versioned anomaly alerts."""

from __future__ import annotations

import json
import hashlib
import math
import os
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from cogniflow_anomaly.detector import ALERT_SCHEMA_VERSION, ALERT_SOURCE, ALERT_TYPE, configured_rules
from preprocessing_api.activity_events import ALLOWED_BACKENDS, MAX_EVENT_BYTES

DELIVERIES = Counter("cogniflow_anomaly_sink_deliveries_total", "Alert sink outcomes.", ["result"])
MAX_ALERTS = 10_000
app = FastAPI(title="CogniFlow anomaly alert sink", docs_url=None, redoc_url=None)


def _connect() -> sqlite3.Connection:
    path = Path(os.getenv("ALERT_STORE_PATH", "/data/alerts.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute("CREATE TABLE IF NOT EXISTS alerts (source TEXT, id TEXT, event_json TEXT NOT NULL, PRIMARY KEY(source,id))")
    return connection


def validate_alert(event: Any) -> dict[str, Any]:
    envelope = {"specversion", "id", "source", "type", "time", "datacontenttype", "data"}
    if not isinstance(event, dict) or set(event) != envelope or event["specversion"] != "1.0" or event["type"] != ALERT_TYPE or event["source"] != ALERT_SOURCE or event["datacontenttype"] != "application/json":
        raise ValueError("invalid alert envelope")
    data = event.get("data")
    required = {"schema_version", "anomaly_id", "rule_id", "rule_version", "detected_at", "window_start", "window_end", "backend", "observed_metric", "threshold", "operator", "sample_count", "severity", "triggering_event_id", "provenance"}
    if not isinstance(data, dict) or set(data) != required or data["schema_version"] != ALERT_SCHEMA_VERSION or data["provenance"] != "synthetic_demo":
        raise ValueError("invalid alert data")
    rule = next((rule for rule in configured_rules() if rule.id == data["rule_id"] and rule.version == data["rule_version"]), None)
    if event["id"] != data["anomaly_id"] or not isinstance(event["id"], str) or len(event["id"]) != 64 or rule is None or data["severity"] != rule.severity:
        raise ValueError("invalid alert identity")
    int(event["id"], 16)
    uuid.UUID(data["triggering_event_id"])
    expected_id = hashlib.sha256(
        f"{rule.id}:{rule.version}:{data['backend']}:{data['triggering_event_id']}".encode()
    ).hexdigest()
    if event["id"] != expected_id:
        raise ValueError("invalid alert identity")
    timestamps = {}
    for key in ("time", "detected_at", "window_start", "window_end"):
        value = event[key] if key == "time" else data[key]
        if not isinstance(value, str):
            raise ValueError("invalid alert timestamp")
        timestamps[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamps[key].tzinfo is None or timestamps[key].utcoffset() != UTC.utcoffset(timestamps[key]):
            raise ValueError("invalid alert timestamp")
    if data["backend"] not in ALLOWED_BACKENDS or data["operator"] != rule.operator:
        raise ValueError("invalid alert rule")
    if type(data["sample_count"]) is not int or data["sample_count"] < rule.minimum_samples:
        raise ValueError("invalid sample count")
    for key in ("observed_metric", "threshold"):
        if type(data[key]) not in {int, float} or not math.isfinite(data[key]):
            raise ValueError("invalid metric")
    triggered = data["observed_metric"] >= rule.threshold if rule.operator == ">=" else data["observed_metric"] > rule.threshold
    if data["threshold"] != rule.threshold or not triggered:
        raise ValueError("invalid alert metric")
    if not (
        timestamps["window_start"] < timestamps["window_end"] <= timestamps["detected_at"]
        and timestamps["time"] <= timestamps["detected_at"]
        and timestamps["window_end"] - timestamps["window_start"] == timedelta(seconds=rule.window_seconds)
    ):
        raise ValueError("invalid alert chronology")
    return event


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    try:
        with _connect() as connection:
            connection.execute("SELECT 1")
    except sqlite3.Error as exc:
        raise HTTPException(503, "alert store unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/")
async def consume(request: Request) -> Response:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_EVENT_BYTES:
            raise HTTPException(413, "alert too large")
        body.extend(chunk)
    try:
        event = validate_alert(json.loads(body))
    except (ValueError, TypeError, json.JSONDecodeError):
        DELIVERIES.labels("invalid").inc()
        raise HTTPException(400, "invalid anomaly alert") from None
    with _connect() as connection:
        inserted = connection.execute("INSERT OR IGNORE INTO alerts VALUES (?, ?, ?)", (event["source"], event["id"], json.dumps(event, separators=(",", ":"), sort_keys=True))).rowcount
        excess = connection.execute("SELECT count(*) - ? FROM alerts", (MAX_ALERTS,)).fetchone()[0]
        if excess > 0:
            connection.execute("DELETE FROM alerts WHERE rowid IN (SELECT rowid FROM alerts ORDER BY rowid LIMIT ?)", (excess,))
    DELIVERIES.labels("accepted" if inserted else "duplicate").inc()
    return Response(status_code=204)
