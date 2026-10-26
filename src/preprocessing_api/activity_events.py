"""Sanitized, best-effort inference activity CloudEvents."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter

EVENT_TYPE = "org.cogniflow.inference.activity.v1"
EVENT_SOURCE = "urn:cogniflow:preprocessing-api"
EVENT_SCHEMA_VERSION = "1.0"
MAX_EVENT_BYTES = 4096
ALLOWED_BACKENDS = {"demo_rule", "local_model", "kserve"}

PUBLISH_EVENTS = Counter(
    "cogniflow_inference_activity_publish_total",
    "Inference activity publication outcomes.",
    ["result"],
)
LOGGER = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def classify_failure(status: int) -> str:
    if 200 <= status < 300:
        return "none"
    if status in {401, 403}:
        return "authentication"
    if status in {400, 422}:
        return "validation"
    if status == 502:
        return "invalid_backend_response"
    if status == 503:
        return "backend_unavailable"
    if status == 504:
        return "backend_timeout"
    return "internal" if status >= 500 else "rejected"


def build_activity_event(
    *, correlation_id: str, status: int, backend: str, latency_ms: float
) -> dict[str, Any]:
    uuid.UUID(correlation_id)
    if backend not in ALLOWED_BACKENDS:
        raise ValueError("unsupported inference backend")
    if not 100 <= status <= 599:
        raise ValueError("invalid HTTP status")
    if not math.isfinite(latency_ms) or not 0 <= latency_ms <= 3_600_000:
        raise ValueError("invalid request latency")
    data: dict[str, Any] = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "correlation_id": correlation_id,
        "outcome": "success" if status < 400 else "failure",
        "http_status": status,
        "inference_backend": backend,
        "latency_ms": round(latency_ms, 3),
        "failure_category": classify_failure(status),
    }
    model_name = os.getenv("MODEL_NAME")
    model_version = os.getenv("MODEL_VERSION")
    if model_name and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", model_name):
        data["model_name"] = model_name
    if model_version and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", model_version):
        data["model_version"] = model_version
    event = {
        "specversion": "1.0",
        "id": str(uuid.uuid4()),
        "source": EVENT_SOURCE,
        "type": EVENT_TYPE,
        "time": _utc_now(),
        "datacontenttype": "application/json",
        "data": data,
    }
    if len(json.dumps(event, separators=(",", ":")).encode()) > MAX_EVENT_BYTES:
        raise ValueError("activity event exceeds size limit")
    return event


def _validated_destination() -> str:
    destination = os.environ["INFERENCE_ACTIVITY_DESTINATION"]
    parsed = urllib.parse.urlsplit(destination)
    host = parsed.hostname or ""
    local = host in {"127.0.0.1", "localhost"}
    cluster_internal = host.endswith(".svc") or host.endswith(".svc.cluster.local")
    if parsed.scheme != "http" or not (local or cluster_internal) or parsed.username:
        raise ValueError("activity destination must be an internal HTTP service")
    if parsed.query or parsed.fragment:
        raise ValueError("activity destination cannot contain a query or fragment")
    return destination


def _timeout_seconds() -> float:
    timeout = float(os.getenv("INFERENCE_ACTIVITY_TIMEOUT_SECONDS", "1"))
    if not math.isfinite(timeout) or not 0 < timeout <= 5:
        raise ValueError("activity timeout must be greater than 0 and at most 5 seconds")
    return timeout


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _post(payload: bytes, destination: str, timeout: float) -> None:
    request = urllib.request.Request(
        destination,
        data=payload,
        headers={"Content-Type": "application/cloudevents+json"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise OSError(f"event receiver returned HTTP {response.status}")


async def publish_activity_event(event: dict[str, Any]) -> bool:
    if os.getenv("INFERENCE_ACTIVITY_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        PUBLISH_EVENTS.labels("disabled").inc()
        return False
    try:
        destination = _validated_destination()
        timeout = _timeout_seconds()
        payload = json.dumps(event, separators=(",", ":")).encode()
        if len(payload) > MAX_EVENT_BYTES:
            raise ValueError("activity event exceeds size limit")
        await asyncio.wait_for(asyncio.to_thread(_post, payload, destination, timeout), timeout + 0.25)
    except (KeyError, ValueError, OSError, TimeoutError, urllib.error.URLError) as exc:
        PUBLISH_EVENTS.labels("failed").inc()
        LOGGER.warning("inference_activity_publish_failed reason=%s", type(exc).__name__)
        return False
    PUBLISH_EVENTS.labels("published").inc()
    return True


class InferenceActivityMiddleware:
    """Publish one sanitized event after each `/predict` response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/predict":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500
        correlation_id = str(uuid.uuid4())

        async def send_with_correlation(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"].append((b"x-correlation-id", correlation_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            try:
                event = build_activity_event(
                    correlation_id=correlation_id,
                    status=status,
                    backend=os.getenv("INFERENCE_MODE", "demo_rule"),
                    latency_ms=(time.perf_counter() - started) * 1000,
                )
                await publish_activity_event(event)
            except (ValueError, RuntimeError) as exc:
                PUBLISH_EVENTS.labels("dropped").inc()
                LOGGER.warning("inference_activity_dropped reason=%s", type(exc).__name__)
