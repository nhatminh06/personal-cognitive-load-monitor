"""Authorized synthetic-only checks for the bounded workers.dev preview."""
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://cogniflow-v01.mphamnhat2006.workers.dev"
client = httpx.Client(base_url=BASE, headers={"Origin": BASE, "X-CogniFlow-CSRF": "1", "Content-Type": "application/json"}, timeout=30)
results = []


def call(method, path, payload=None, status=200, headers=None):
    response = client.request(method, path, json=payload, headers=headers)
    assert response.status_code == status, (method, path, response.status_code, response.text[:200])
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("x-frame-options") == "DENY"
    assert "frame-ancestors 'none'" in response.headers.get("content-security-policy", "")
    results.append({"method": method, "path": path.split("?")[0], "status": status})
    return response


def event(sid, when, sequence, kind):
    return {"schema_version": "1.0", "event_id": str(uuid4()), "session_id": sid,
            "event_time": when.isoformat(), "ingested_at": datetime.now(UTC).isoformat(),
            "source": "synthetic_live_qualification", "producer_version": "1.0.0",
            "idempotency_key": str(uuid4()), "event_type": kind, "sequence": sequence,
            "session_kind": "study", "privacy_mode": "behavioral"}


def main():
    call("GET", "/focus")
    call("GET", "/focus-assets/dashboard.js")
    call("GET", "/sessions/auth-check", status=401)
    call("GET", "/sessions/private", status=401)
    credential = (ROOT / ".owner-credential-ts-final").read_text().strip()
    call("POST", "/auth/login", {"credential": credential}, 403, {"Origin": "https://attacker.invalid"})
    login = call("POST", "/auth/login", {"credential": credential})
    cookie = login.headers["set-cookie"]
    assert all(part in cookie.lower() for part in ("secure", "httponly", "samesite=strict", "path=/"))
    client.headers["Cookie"] = cookie.split(";", 1)[0]
    call("GET", "/sessions/auth-check")
    call("POST", "/sessions", {}, 403, {"X-CogniFlow-CSRF": ""})
    call("POST", "/sessions", {}, 422)
    sid = "synthetic-live-" + str(uuid4())
    start = datetime.now(UTC) - timedelta(minutes=20)
    first = event(sid, start, 1, "session.started")
    call("POST", "/sessions", first, 201)
    call("POST", "/sessions", first, 200)
    for seq, minute, kind in ((2, 6, "paused"), (3, 8, "resumed"), (4, 14, "completed")):
        call("POST", f"/sessions/{sid}/transitions", event(sid, start + timedelta(minutes=minute), seq, "session." + kind))
    session = call("GET", f"/sessions/{sid}").json()
    assert session["confirmed_active_seconds"] == 720 and len(session["completed_windows"]) == 2
    window = session["completed_windows"][0]
    assert window["window_start"].split(".")[1][:6] == start.isoformat().split(".")[1][:6]
    now = datetime.now(UTC).isoformat()
    label = {"event_id": str(uuid4()), "idempotency_key": str(uuid4()), "session_id": sid,
             "source": "synthetic_live_qualification", "producer_version": "1.0.0",
             "event_time": now, "ingested_at": now, "reported_at": now,
             "feature_cutoff": window["window_end"], **window, "label_id": str(uuid4()), "effort_rating": 6}
    assert call("POST", f"/sessions/{sid}/labels", label, 201).json()["compatibility_band"] == "HIGH"
    call("POST", f"/sessions/{sid}/labels", label)
    timeline = call("GET", f"/sessions/{sid}/timeline?limit=100").json()
    assert timeline["total"] == 7 and len(timeline["items"]) == 7
    call("GET", f"/sessions/{sid}/timeline?limit=2&offset=2")
    call("GET", f"/sessions/{sid}/timeline?limit=101", status=422)
    call("GET", "/sessions/does-not-exist", status=404)
    call("POST", f"/sessions/{sid}/transitions", event(sid, datetime.now(UTC), 5, "session.paused"), 409)
    estimate = call("POST", "/predict", {"focus_minutes": 60, "distraction_minutes": 10,
                                         "tasks_due": 2, "hours_to_deadline": 24}).json()
    assert estimate["inference_source"] == "demo_rule"
    assert call("GET", "/estimates").json()["items"]
    call("GET", "/model-info")
    with httpx.Client(base_url=BASE, headers={"Cookie": "__Host-cogniflow=invalid"}, timeout=30) as outsider:
        assert outsider.get(f"/sessions/{sid}").status_code == 401
        assert outsider.get(f"/sessions/{sid}/timeline").status_code == 401
    call("POST", "/auth/logout", {})
    call("GET", f"/sessions/{sid}", status=401)
    artifact = ROOT.parents[1] / "build/cloudflare-ts-live-functional.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps({"result": "PASS", "requests": results, "synthetic_session": sid}, indent=2) + "\n")
    print(f"PASS: {len(results)} synthetic live requests; sha256 {hashlib.sha256(artifact.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
