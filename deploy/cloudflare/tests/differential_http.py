"""Compare the public Python and TypeScript HTTP contracts on local Workers only."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
PORTS = (18787, 18788)
clients = [httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30) for port in PORTS]
observations = []


def stable(value):
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items()
                if key not in {"ingested_at", "created_at", "estimate_id"}}
    if isinstance(value, list):
        return [stable(item) for item in value]
    if isinstance(value, str) and value.endswith("Z") and "T" in value:
        return value[:-1] + "+00:00"
    return value


def check(method, path, payload=None, *, headers=None, expected=None):
    responses = []
    for client, port in zip(clients, PORTS):
        base = f"http://127.0.0.1:{port}"
        request_headers = {"Origin": base, "X-CogniFlow-CSRF": "1", "Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        response = client.request(method, path, json=payload, headers=request_headers)
        responses.append(response)
    left, right = responses
    assert left.status_code == right.status_code, (method, path, left.status_code, right.status_code, left.text[:300], right.text[:300])
    if expected is not None:
        assert left.status_code == expected, (method, path, left.status_code, left.text[:300])
    for key in ("content-type", "cache-control", "x-content-type-options", "x-frame-options", "referrer-policy", "strict-transport-security", "permissions-policy", "content-security-policy"):
        assert left.headers.get(key) == right.headers.get(key), (method, path, key, left.headers.get(key), right.headers.get(key))
    if "application/json" in left.headers.get("content-type", ""):
        a, b = stable(left.json()), stable(right.json())
        assert a == b, (method, path, a, b)
    observations.append({"method": method, "path": path, "status": left.status_code})
    return responses


def event(sid, at, sequence, kind):
    return {"schema_version": "1.0", "event_id": str(uuid4()), "session_id": sid,
            "event_time": at.isoformat(), "ingested_at": datetime.now(UTC).isoformat(),
            "source": "differential_test", "producer_version": "1.0.0", "idempotency_key": str(uuid4()),
            "event_type": kind, "sequence": sequence, "session_kind": "study", "privacy_mode": "behavioral"}


def main():
    sid = "synthetic-diff-" + str(uuid4())
    now = datetime.now(UTC)
    for path in ("/sessions/auth-check", f"/sessions/{sid}", "/estimates", "/model-info"):
        check("GET", path, expected=401)
    credential = (ROOT / ".local-credential").read_text()
    check("POST", "/auth/login", {"credential": credential}, headers={"Origin": "https://attacker.invalid"}, expected=403)
    for client, response in zip(clients, check("POST", "/auth/login", {"credential": credential}, expected=200)):
        cookie = response.headers["set-cookie"]
        assert all(part in cookie.lower() for part in ("secure", "httponly", "samesite=strict", "path=/"))
        client.headers["Cookie"] = cookie.split(";", 1)[0]
    check("GET", "/sessions/auth-check", expected=200)
    check("POST", "/sessions", {}, headers={"X-CogniFlow-CSRF": ""}, expected=403)
    check("POST", "/sessions", {}, expected=422)
    check("POST", "/sessions", {"huge": "x" * 17000}, expected=413)
    check("GET", f"/sessions/{sid}", expected=404)
    start = now - timedelta(minutes=20)
    first = event(sid, start, 1, "session.started")
    check("POST", "/sessions", first, expected=201)
    check("POST", "/sessions", first, expected=200)
    for seq, minute, kind in ((2, 6, "paused"), (3, 8, "resumed"), (4, 14, "completed")):
        transition = event(sid, start + timedelta(minutes=minute), seq, "session." + kind)
        check("POST", f"/sessions/{sid}/transitions", transition, expected=200)
    session = check("GET", f"/sessions/{sid}", expected=200)[0].json()
    assert session["confirmed_active_seconds"] == 720 and len(session["completed_windows"]) == 2
    window = session["completed_windows"][0]
    timestamp = datetime.now(UTC).isoformat()
    label = {"event_id": str(uuid4()), "idempotency_key": str(uuid4()), "session_id": sid,
             "source": "differential_test", "producer_version": "1.0.0", "event_time": timestamp,
             "ingested_at": timestamp, "reported_at": timestamp, "feature_cutoff": window["window_end"],
             **window, "label_id": str(uuid4()), "effort_rating": 6}
    check("POST", f"/sessions/{sid}/labels", label, expected=201)
    check("POST", f"/sessions/{sid}/labels", label, expected=200)
    correction = {**label, "event_id": str(uuid4()), "idempotency_key": str(uuid4()),
                  "label_id": str(uuid4()), "supersedes_label_id": label["label_id"], "effort_rating": 3}
    check("POST", f"/sessions/{sid}/labels", correction, expected=201)
    check("POST", f"/sessions/{sid}/labels", {**label, "event_id": str(uuid4()),
                                                "idempotency_key": str(uuid4())}, expected=409)
    active_sid = "synthetic-diff-active-" + str(uuid4())
    check("POST", "/sessions", event(active_sid, now - timedelta(minutes=7), 1, "session.started"), expected=201)
    active = check("POST", f"/sessions/{active_sid}/windows/refresh", {}, expected=200)[0].json()
    active_window = active["completed_windows"][0]
    check("POST", f"/sessions/{active_sid}/windows/refresh", {}, expected=200)
    activity = {"event_id": str(uuid4()), "idempotency_key": str(uuid4()), "session_id": active_sid,
                "source": "differential_test", "producer_version": "1.0.0",
                "event_time": active_window["window_end"], "ingested_at": timestamp,
                "feature_cutoff": active_window["window_end"], **active_window,
                "active_seconds": 240, "idle_seconds": 60, "keyboard_event_count": 10,
                "pointer_event_count": 2, "application_switch_count": 1}
    check("POST", f"/sessions/{active_sid}/activity-windows", activity, expected=201)
    check("POST", f"/sessions/{active_sid}/activity-windows", activity, expected=200)
    check("GET", f"/sessions/{sid}/timeline?limit=2&offset=1", expected=200)
    check("GET", f"/sessions/{sid}/timeline?limit=101", expected=422)
    check("POST", f"/sessions/{sid}/transitions", event(sid, now, 5, "session.paused"), expected=409)
    check("POST", "/predict", {"focus_minutes": 60, "distraction_minutes": 10,
                                 "tasks_due": 2, "hours_to_deadline": 24}, expected=200)
    check("GET", "/estimates", expected=200)
    check("GET", "/model-info", expected=200)
    check("POST", "/auth/logout", {}, expected=200)
    check("GET", f"/sessions/{sid}", expected=401)
    check("POST", "/predict", {"focus_minutes": 1, "distraction_minutes": 0,
                                 "tasks_due": 0, "hours_to_deadline": 24}, expected=401)
    result = ROOT.parents[1] / "build/cloudflare-ts-differential.json"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(json.dumps({"result": "PASS", "requests": observations}, indent=2) + "\n")
    print(f"PASS: {len(observations)} differential requests; sha256 {hashlib.sha256(result.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
