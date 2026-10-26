"""Strict CloudEvents consumer with durable SQLite deduplication."""

from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from preprocessing_api.activity_events import (
    ALLOWED_BACKENDS,
    EVENT_SOURCE,
    EVENT_SCHEMA_VERSION,
    EVENT_TYPE,
    MAX_EVENT_BYTES,
)

DELIVERIES = Counter(
    "cogniflow_event_consumer_deliveries_total",
    "Consumer delivery outcomes.",
    ["result"],
)
app = FastAPI(title="CogniFlow activity event consumer", docs_url=None, redoc_url=None)


def _store_path() -> Path:
    return Path(os.getenv("EVENT_STORE_PATH", "/data/events.sqlite3"))


def _connection() -> sqlite3.Connection:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS events ("
        "source TEXT NOT NULL, id TEXT NOT NULL, received_at TEXT NOT NULL, event_json TEXT NOT NULL, "
        "PRIMARY KEY (source, id))"
    )
    return connection


def validate_event(event: Any) -> dict[str, Any]:
    if not isinstance(event, dict) or set(event) != {
        "specversion", "id", "source", "type", "time", "datacontenttype", "data"
    }:
        raise ValueError("invalid CloudEvent envelope")
    if event["specversion"] != "1.0" or event["type"] != EVENT_TYPE:
        raise ValueError("unsupported CloudEvent version or type")
    if event["datacontenttype"] != "application/json" or event["source"] != EVENT_SOURCE:
        raise ValueError("invalid CloudEvent metadata")
    if not isinstance(event["id"], str):
        raise ValueError("invalid CloudEvent id")
    uuid.UUID(event["id"])
    timestamp = datetime.fromisoformat(str(event["time"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ValueError("CloudEvent time must be UTC")
    data = event["data"]
    required = {
        "schema_version", "correlation_id", "outcome", "http_status",
        "inference_backend", "latency_ms", "failure_category",
    }
    optional = {"model_name", "model_version"}
    if not isinstance(data, dict) or not required <= set(data) or not set(data) - required <= optional:
        raise ValueError("invalid activity data schema")
    if not isinstance(data["correlation_id"], str):
        raise ValueError("invalid correlation id")
    uuid.UUID(data["correlation_id"])
    if data["schema_version"] != EVENT_SCHEMA_VERSION:
        raise ValueError("unsupported activity schema")
    if data["outcome"] not in {"success", "failure"}:
        raise ValueError("invalid outcome")
    if type(data["http_status"]) is not int or not 100 <= data["http_status"] <= 599:
        raise ValueError("invalid status")
    if data["inference_backend"] not in ALLOWED_BACKENDS:
        raise ValueError("invalid inference backend")
    if (
        type(data["latency_ms"]) not in {int, float}
        or not math.isfinite(data["latency_ms"])
        or not 0 <= data["latency_ms"] <= 3_600_000
    ):
        raise ValueError("invalid latency")
    if data["failure_category"] not in {
        "none", "authentication", "validation", "invalid_backend_response",
        "backend_unavailable", "backend_timeout", "internal", "rejected",
    }:
        raise ValueError("invalid failure category")
    expected_outcome = "success" if data["http_status"] < 400 else "failure"
    invalid_category = (
        expected_outcome == "success" and data["failure_category"] != "none"
    ) or (expected_outcome == "failure" and data["failure_category"] == "none")
    if data["outcome"] != expected_outcome or invalid_category:
        raise ValueError("inconsistent outcome")
    for key in ("model_name", "model_version"):
        if key in data and (not isinstance(data[key], str) or len(data[key]) > 128):
            raise ValueError("invalid model identity")
    return event


def parse_delivery(body: bytes, headers: Any) -> dict[str, Any]:
    """Normalize structured and Knative's binary CloudEvents representation."""
    content_type = headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type == "application/cloudevents+json":
        return validate_event(json.loads(body))
    required_headers = ("ce-specversion", "ce-id", "ce-source", "ce-type", "ce-time")
    if not all(headers.get(name) for name in required_headers):
        raise ValueError("missing binary CloudEvent headers")
    return validate_event(
        {
            "specversion": headers["ce-specversion"],
            "id": headers["ce-id"],
            "source": headers["ce-source"],
            "type": headers["ce-type"],
            "time": headers["ce-time"],
            "datacontenttype": content_type,
            "data": json.loads(body),
        }
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    try:
        with _connection() as connection:
            connection.execute("SELECT 1")
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="event store unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/")
async def consume(request: Request) -> Response:
    if os.getenv("CONSUMER_FORCE_FAILURE", "false").lower() in {"1", "true", "yes"}:
        DELIVERIES.labels("failed").inc()
        raise HTTPException(status_code=503, detail="consumer temporarily unavailable")
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
            if length < 0:
                raise ValueError
            too_large = length > MAX_EVENT_BYTES
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid content length") from None
        if too_large:
            DELIVERIES.labels("rejected").inc()
            raise HTTPException(status_code=413, detail="event too large")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_EVENT_BYTES:
            DELIVERIES.labels("rejected").inc()
            raise HTTPException(status_code=413, detail="event too large")
        body.extend(chunk)
    try:
        event = parse_delivery(bytes(body), request.headers)
    except (ValueError, TypeError, json.JSONDecodeError):
        DELIVERIES.labels("rejected").inc()
        raise HTTPException(status_code=400, detail="invalid activity event") from None
    serialized = json.dumps(event, separators=(",", ":"), sort_keys=True)
    try:
        with _connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO events(source, id, received_at, event_json) VALUES (?, ?, ?, ?)",
                (event["source"], event["id"], datetime.now(UTC).isoformat(), serialized),
            )
    except sqlite3.Error as exc:
        DELIVERIES.labels("failed").inc()
        raise HTTPException(status_code=503, detail="event persistence failed") from exc
    DELIVERIES.labels("accepted" if cursor.rowcount else "duplicate").inc()
    return Response(status_code=204)
