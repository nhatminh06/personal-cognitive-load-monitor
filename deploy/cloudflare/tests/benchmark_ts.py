"""Local-only HTTP timing; temporary bench config raises rate counters to avoid 429."""
import hashlib
import json
import statistics
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:18787"
RESULT = ROOT.parents[1] / "build/cloudflare-ts-benchmark.json"
client = httpx.Client(base_url=BASE, headers={"Origin": BASE, "X-CogniFlow-CSRF": "1", "Content-Type": "application/json"}, timeout=30)
measurements = {}


def measure(name, method, path, payload=None, statuses=(200,)):
    start = time.perf_counter_ns()
    response = client.request(method, path, json=payload)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    assert response.status_code in statuses, (name, response.status_code, response.text[:120])
    measurements.setdefault(name, []).append(elapsed)
    return response


def event(sid, at, kind="session.started", sequence=1):
    return {"schema_version": "1.0", "event_id": str(uuid4()), "session_id": sid,
            "event_time": at.isoformat(), "ingested_at": datetime.now(UTC).isoformat(),
            "source": "synthetic_bench", "producer_version": "1.0.0", "idempotency_key": str(uuid4()),
            "event_type": kind, "sequence": sequence, "session_kind": "study", "privacy_mode": "behavioral"}


def run():
    credential = (ROOT / ".local-credential").read_text()
    measure("health_cold", "GET", "/health")
    for _ in range(30):
        measure("health", "GET", "/health")
    for _ in range(30):
        login = measure("login", "POST", "/auth/login", {"credential": credential})
        client.headers["Cookie"] = login.headers["set-cookie"].split(";", 1)[0]
    for _ in range(30):
        measure("auth_check", "GET", "/sessions/auth-check")
    records = []
    for _ in range(30):
        sid = "synthetic-bench-" + str(uuid4())
        start = datetime.now(UTC) - timedelta(minutes=7)
        first = event(sid, start)
        measure("create", "POST", "/sessions", first, (201,))
        records.append((sid, start))
    for sid, start in records:
        measure("transition", "POST", f"/sessions/{sid}/transitions",
                event(sid, start + timedelta(minutes=6), "session.completed", 2))
    for sid, _ in records:
        session = client.get(f"/sessions/{sid}").json()
        w = session["completed_windows"][0]
        now = datetime.now(UTC).isoformat()
        label = {"event_id": str(uuid4()), "idempotency_key": str(uuid4()), "session_id": sid,
                 "source": "synthetic_bench", "producer_version": "1.0.0", "event_time": now,
                 "ingested_at": now, "reported_at": now, "feature_cutoff": w["window_end"],
                 **w, "label_id": str(uuid4()), "effort_rating": 5}
        measure("label", "POST", f"/sessions/{sid}/labels", label, (201,))
    for sid, _ in records:
        measure("timeline", "GET", f"/sessions/{sid}/timeline?limit=50")
    body = {"focus_minutes": 60, "distraction_minutes": 10, "tasks_due": 2, "hours_to_deadline": 24}
    for _ in range(30):
        measure("predict", "POST", "/predict", body)
    summary = {name: {"n": len(values), "median_ms": round(statistics.median(values), 3),
                      "p95_ms": round(sorted(values)[int(.95 * (len(values) - 1))], 3),
                      "max_ms": round(max(values), 3)} for name, values in measurements.items()}
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps({"kind": "local HTTP wall time, not Worker CPU", "summary": summary}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("sha256", hashlib.sha256(RESULT.read_bytes()).hexdigest())


if __name__ == "__main__":
    run()
