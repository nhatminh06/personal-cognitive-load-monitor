"""Paced synthetic-only CPU workload; never accepts a configurable remote host."""
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://cogniflow-v01.mphamnhat2006.workers.dev"
client = httpx.Client(base_url=BASE, headers={"Origin": BASE, "X-CogniFlow-CSRF": "1", "Content-Type": "application/json"}, timeout=30)
phases = []
samples = []


def iso():
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def call(method, path, payload=None, expected=200):
    response = client.request(method, path, json=payload)
    assert response.status_code == expected, (method, path, response.status_code, response.text[:160])
    assert "Worker exceeded resource limits" not in response.text
    return response


def event(sid, at, sequence, kind):
    return {"schema_version": "1.0", "event_id": str(uuid4()), "session_id": sid,
            "event_time": at.isoformat(), "ingested_at": datetime.now(UTC).isoformat(),
            "source": "synthetic_cpu_qualification", "producer_version": "1.0.0",
            "idempotency_key": str(uuid4()), "event_type": kind, "sequence": sequence,
            "session_kind": "study", "privacy_mode": "behavioral"}


def phase(name, requests):
    time.sleep(2)
    start = iso()
    for index, request in enumerate(requests, 1):
        response = request()
        samples.append({"endpoint": name, "index": index, "at": iso(),
                        "status": response.status_code, "ray_id": response.headers.get("cf-ray")})
        time.sleep(1.15)
    end = iso()
    phases.append({"endpoint": name, "count": len(requests), "start": start, "end": end, "errors": 0})
    print(f"PASS {name}: {len(requests)} HTTPS requests", flush=True)


def main():
    credential = (ROOT / ".owner-credential-ts-final").read_text().strip()
    login = call("POST", "/auth/login", {"credential": credential})
    client.headers["Cookie"] = login.headers["set-cookie"].split(";", 1)[0]
    phase("health", [lambda: call("GET", "/health") for _ in range(30)])
    phase("auth_check", [lambda: call("GET", "/sessions/auth-check") for _ in range(30)])
    records = [("synthetic-cpu-" + str(uuid4()), datetime.now(UTC) - timedelta(minutes=7)) for _ in range(30)]
    phase("create", [lambda sid=sid, at=at: call("POST", "/sessions", event(sid, at, 1, "session.started"), 201)
                     for sid, at in records])
    phase("transition", [lambda sid=sid, at=at: call("POST", f"/sessions/{sid}/transitions",
                                     event(sid, at + timedelta(minutes=6), 2, "session.completed"))
                         for sid, at in records])
    labels = []
    for sid, _ in records:
        window = call("GET", f"/sessions/{sid}").json()["completed_windows"][0]
        now = datetime.now(UTC).isoformat()
        labels.append((sid, {"event_id": str(uuid4()), "idempotency_key": str(uuid4()), "session_id": sid,
                             "source": "synthetic_cpu_qualification", "producer_version": "1.0.0",
                             "event_time": now, "ingested_at": now, "reported_at": now,
                             "feature_cutoff": window["window_end"], **window,
                             "label_id": str(uuid4()), "effort_rating": 5}))
    phase("label", [lambda sid=sid, body=body: call("POST", f"/sessions/{sid}/labels", body, 201)
                    for sid, body in labels])
    phase("timeline", [lambda sid=sid: call("GET", f"/sessions/{sid}/timeline?limit=50")
                       for sid, _ in records])
    body = {"focus_minutes": 60, "distraction_minutes": 10, "tasks_due": 2, "hours_to_deadline": 24}
    phase("estimate", [lambda: call("POST", "/predict", body) for _ in range(30)])
    # Login is intentionally sampled below its 5/minute abuse limit.
    time.sleep(61)
    start = iso()
    for index in range(1, 31):
        response = call("POST", "/auth/login", {"credential": credential})
        samples.append({"endpoint": "login", "index": index, "at": iso(),
                        "status": response.status_code, "ray_id": response.headers.get("cf-ray")})
        client.headers["Cookie"] = response.headers["set-cookie"].split(";", 1)[0]
        time.sleep(14)
    phases.append({"endpoint": "login", "count": 30, "start": start, "end": iso(), "errors": 0,
                   "note": "paced below production 5/minute abuse binding"})
    output = ROOT.parents[1] / "build/cloudflare-ts-live-cpu-workload.json"
    output.write_text(json.dumps({"phases": phases, "samples": samples}, indent=2) + "\n")
    print("sha256", hashlib.sha256(output.read_bytes()).hexdigest(), flush=True)


if __name__ == "__main__":
    main()
