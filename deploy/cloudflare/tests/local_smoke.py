"""Synthetic HTTP tests against local workerd/D1 only. Never accepts a remote URL."""
import os
import concurrent.futures
import json
from pathlib import Path
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:18787"
HEADERS = {"Origin": BASE, "X-CogniFlow-CSRF": "1", "Content-Type": "application/json"}
samples = []
client = httpx.Client(base_url=BASE, headers=HEADERS, timeout=30)


def call(method, path, payload=None, expected=200, **kwargs):
    started = time.perf_counter()
    response = client.request(method, path, json=payload, **kwargs)
    samples.append((path, (time.perf_counter() - started) * 1000))
    assert response.status_code == expected, (path, response.status_code, response.text[:200])
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "access-control-allow-origin" not in response.headers
    return response


def event(sid, when, sequence=1, kind="session.started"):
    return {"schema_version": "1.0", "event_id": str(uuid4()), "session_id": sid,
            "event_time": when.isoformat(), "ingested_at": datetime.now(UTC).isoformat(),
            "source": "synthetic_test", "producer_version": "1.0.0", "idempotency_key": str(uuid4()),
            "event_type": kind, "sequence": sequence, "session_kind": "study", "privacy_mode": "behavioral"}


def main():
    for path in ("/focus", "/focus-assets/dashboard.js", "/focus-assets/dashboard.css", "/focus-assets/dashboard-state.js"):
        call("GET", path)
    for path in ("/sessions/auth-check", "/sessions/private", "/estimates", "/model-info"):
        call("GET", path, expected=401)
    for path in ("/health", "/ready"):
        call("GET", path, expected=200 if os.getenv("COGNIFLOW_TS") else 404)
    for path in ("/metrics", "/docs", "/openapi.json", "/v1/focus/health"):
        call("GET", path, expected=404)
    credential = (ROOT / ".local-credential").read_text()
    call("POST", "/auth/login", {"credential": credential}, expected=403,
         headers={**HEADERS, "Origin": "https://attacker.invalid"})
    for origin in ("https://cogniflow.minhpham06.com",):
        response = call("POST", "/auth/login", {"credential": credential},
                        headers={**HEADERS, "Origin": origin})
        assert "__Host-cogniflow=" in response.headers["set-cookie"]
        call("POST", "/auth/logout", {}, headers={**HEADERS, "Origin": origin,
             "Cookie": response.headers["set-cookie"].split(";", 1)[0]})
    for origin in ("https://evil.minhpham06.com", "http://cogniflow.minhpham06.com",
                   "https://cogniflow.minhpham06.com.evil.invalid", "null", ""):
        call("POST", "/auth/login", {"credential": credential}, expected=403,
             headers={**HEADERS, "Origin": origin})
    response = call("POST", "/auth/login", {"credential": credential})
    cookie = response.headers["set-cookie"]
    assert all(part in cookie.lower() for part in ("httponly", "secure", "samesite=strict", "path=/"))
    client.headers["Cookie"] = cookie.split(";", 1)[0]
    call("GET", "/sessions/auth-check")
    alternate_sid = "synthetic-origin-" + str(uuid4())
    call("POST", "/sessions", event(alternate_sid, datetime.now(UTC)), 201,
         headers={**HEADERS, "Origin": "https://cogniflow.minhpham06.com"})
    assert call("GET", f"/sessions/{alternate_sid}").json()["session_id"] == alternate_sid
    call("POST", "/sessions", event("blocked-" + str(uuid4()), datetime.now(UTC)), 403,
         headers={**HEADERS, "Origin": "https://evil.minhpham06.com"})
    call("POST", "/sessions", {}, expected=403, headers={**HEADERS, "X-CogniFlow-CSRF": ""})
    call("POST", "/sessions", {}, expected=422)
    call("POST", "/sessions", {"huge": "x" * 17000}, expected=413)
    sid = "synthetic-" + str(uuid4())
    start = datetime.now(UTC) - timedelta(minutes=20)
    first = event(sid, start)
    results = list(concurrent.futures.ThreadPoolExecutor(3).map(
        lambda _: client.post("/sessions", json=first), range(3)))
    assert sorted(r.status_code for r in results) == [200, 200, 201], [(r.status_code, r.text) for r in results]
    pause = event(sid, start + timedelta(minutes=6), 2, "session.paused")
    other = event(sid, start + timedelta(minutes=6), 2, "session.completed")
    results = list(concurrent.futures.ThreadPoolExecutor(2).map(
        lambda e: client.post(f"/sessions/{sid}/transitions", json=e), [pause, other]))
    assert sorted(r.status_code for r in results) == [200, 409]
    # Resume/complete on a separate deterministic lifecycle so both race outcomes are valid.
    sid2 = "synthetic-" + str(uuid4())
    call("POST", "/sessions", event(sid2, start), 201)
    for seq, minute, kind in [(2, 6, "paused"), (3, 8, "resumed"), (4, 14, "completed")]:
        call("POST", f"/sessions/{sid2}/transitions", event(sid2, start + timedelta(minutes=minute), seq, "session." + kind))
    session = call("GET", f"/sessions/{sid2}").json()
    assert session["confirmed_active_seconds"] == 720
    assert len(session["completed_windows"]) == 2
    window = session["completed_windows"][0]
    now = datetime.now(UTC).isoformat()
    label = {"event_id": str(uuid4()), "idempotency_key": str(uuid4()), "session_id": sid2,
             "source": "synthetic_test", "producer_version": "1.0.0", "event_time": now,
             "ingested_at": now, "reported_at": now, "feature_cutoff": window["window_end"],
             **window, "label_id": str(uuid4()), "effort_rating": 6}
    result = call("POST", f"/sessions/{sid2}/labels", label, 201).json()
    assert result["compatibility_band"] == "HIGH"
    call("POST", f"/sessions/{sid2}/labels", label)
    correction = {**label, "event_id": str(uuid4()), "idempotency_key": str(uuid4()),
                  "label_id": str(uuid4()), "supersedes_label_id": label["label_id"], "effort_rating": 3}
    call("POST", f"/sessions/{sid2}/labels", correction, 201)
    call("POST", f"/sessions/{sid2}/labels", {**label, "event_id": str(uuid4()), "idempotency_key": str(uuid4())}, 409)
    timeline = call("GET", f"/sessions/{sid2}/timeline?limit=100").json()
    assert timeline["total"] == 8
    assert len(call("GET", f"/sessions/{sid2}/timeline?limit=2&offset=2").json()["items"]) == 2
    call("GET", f"/sessions/{sid2}/timeline?limit=101", expected=422)
    call("GET", "/sessions/missing", expected=404)
    active_sid = "synthetic-refresh-" + str(uuid4())
    call("POST", "/sessions", event(active_sid, datetime.now(UTC) - timedelta(minutes=6)), 201)
    refreshed = call("POST", f"/sessions/{active_sid}/windows/refresh").json()
    assert len(refreshed["completed_windows"]) == 1
    assert call("POST", f"/sessions/{active_sid}/windows/refresh").json()["completed_windows"] == refreshed["completed_windows"]
    active_window = refreshed["completed_windows"][0]
    behavioral = {"event_id": str(uuid4()), "idempotency_key": str(uuid4()), "session_id": active_sid,
                  "source": "synthetic_test", "producer_version": "1.0.0", "event_time": active_window["window_end"],
                  "ingested_at": datetime.now(UTC).isoformat(), "feature_cutoff": active_window["window_end"],
                  **active_window, "active_seconds": 240, "idle_seconds": 60, "keyboard_event_count": 10,
                  "pointer_event_count": 2, "application_switch_count": 1}
    call("POST", f"/sessions/{active_sid}/activity-windows", behavioral, 201)
    call("POST", f"/sessions/{active_sid}/activity-windows", behavioral)
    call("POST", f"/sessions/{active_sid}/activity-windows", {**behavioral, "event_id": str(uuid4()), "idempotency_key": str(uuid4())}, 409)
    estimate = call("POST", "/predict", {"focus_minutes": 60, "distraction_minutes": 10,
                                          "tasks_due": 2, "hours_to_deadline": 24}).json()
    assert estimate["inference_source"] == "demo_rule" and estimate["model_version"] is None
    assert call("GET", "/estimates").json()["items"][0]["inference_source"] == "demo_rule"
    heavy = "synthetic-heavy-" + str(uuid4())
    when = datetime.now(UTC) - timedelta(hours=9)
    call("POST", "/sessions", event(heavy, when), 201)
    call("POST", f"/sessions/{heavy}/transitions", event(heavy, when + timedelta(hours=8), 2, "session.completed"))
    assert len(call("GET", f"/sessions/{heavy}").json()["completed_windows"]) == 96
    call("GET", f"/sessions/{heavy}/timeline?limit=100")
    # Keep a non-secret ID for the separate restart verification.
    (ROOT / ".wrangler/restart-session").write_text(sid2)
    call("POST", "/auth/logout", {})
    call("GET", "/sessions/auth-check", expected=401)
    assert client.post("/sessions", json=first).status_code == 401
    assert client.post(f"/sessions/{sid2}/transitions", json=first).status_code == 401
    assert client.post(f"/sessions/{sid2}/labels", json=label).status_code == 401
    assert client.post("/predict", json={"focus_minutes": 1, "distraction_minutes": 0, "tasks_due": 0, "hours_to_deadline": 24}).status_code == 401
    print(json.dumps({"result": "PASS", "requests_timed": len(samples),
                      "wall_ms_median": round(statistics.median(v for _, v in samples), 2),
                      "wall_ms_max": round(max(v for _, v in samples), 2),
                      "heavy_requests": [(p, round(v, 2)) for p, v in samples if heavy in p],
                      "qualification": "local workerd only; wall time is not Workers CPU"}, indent=2))


if __name__ == "__main__":
    if "--restart-check" in sys.argv:
        response = call("POST", "/auth/login", {"credential": (ROOT / ".local-credential").read_text()})
        client.headers["Cookie"] = response.headers["set-cookie"].split(";", 1)[0]
        sid = (ROOT / ".wrangler/restart-session").read_text()
        persisted = call("GET", f"/sessions/{sid}").json()
        assert persisted["state"] == "session.completed" and len(persisted["completed_windows"]) == 2
        assert call("GET", f"/sessions/{sid}/timeline").json()["total"] >= 8
        assert call("GET", "/estimates").json()["items"]
        call("POST", "/auth/logout", {})
        print("PASS: local D1 session/windows/labels/timeline/demo_rule history survived Worker restart")
    else:
        main()
