"""Exercise the isolated MVP with synthetic data only."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def request(base: str, path: str, key: str | None = None, payload: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    req = Request(
        f"{base}{path}", headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
    )
    with urlopen(req, timeout=10) as response:
        return json.load(response)


def event(session_id: str, kind: str, sequence: int, when: datetime) -> dict:
    return {
        "schema_version": "1.0", "event_id": str(uuid4()), "session_id": session_id,
        "event_time": when.isoformat(), "ingested_at": when.isoformat(),
        "source": "mvp_synthetic_smoke", "producer_version": "1.0.0",
        "idempotency_key": f"mvp-smoke:{session_id}:{sequence}",
        "event_type": f"session.{kind}", "sequence": sequence,
        "session_kind": "programming", "privacy_mode": "behavioral",
        "planned_duration_seconds": 600,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--secret", type=Path, default=Path("build/mvp/cogniflow_api_key"))
    args = parser.parse_args()
    key = args.secret.read_text(encoding="utf-8").strip()

    assert request(args.base_url, "/health") == {"status": "healthy"}
    ready = request(args.base_url, "/ready")
    assert ready == {"status": "ready", "inference_mode": "demo_rule"}
    try:
        request(args.base_url, "/sessions/auth-check")
    except HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("unauthenticated session access did not fail")
    assert request(args.base_url, "/sessions/auth-check", key) == {"authenticated": True}

    session_id = f"mvp-synthetic-{uuid4()}"
    started = datetime.now(UTC) - timedelta(minutes=6)
    request(args.base_url, "/sessions", key, event(session_id, "started", 1, started))
    request(
        args.base_url, f"/sessions/{session_id}/transitions", key,
        event(session_id, "completed", 2, started + timedelta(minutes=6)),
    )
    session = request(args.base_url, f"/sessions/{session_id}", key)
    assert session["state"] == "session.completed" and len(session["completed_windows"]) == 1

    estimate = json.loads(Path("examples/mvp/synthetic-estimate.json").read_text(encoding="utf-8"))
    prediction = request(args.base_url, "/predict", key, estimate)
    assert prediction["inference_source"] == "demo_rule" and prediction["model_version"] is None
    print(json.dumps({"status": "PASS", "session_id": session_id, "prediction": prediction}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
