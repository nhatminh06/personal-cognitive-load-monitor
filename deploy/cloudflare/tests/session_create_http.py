"""Bounded synthetic concurrency check against the local TypeScript Worker."""
import concurrent.futures
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

BASE = "http://127.0.0.1:18787"
ROOT = Path(__file__).resolve().parents[1]
HEADERS = {"Origin": BASE, "X-CogniFlow-CSRF": "1", "Content-Type": "application/json"}


def main():
    with httpx.Client(base_url=BASE, headers=HEADERS, timeout=30) as client:
        login = client.post("/auth/login", json={"credential": (ROOT / ".local-credential").read_text()})
        assert login.status_code == 200, (login.status_code, login.text)
        headers = {**HEADERS, "Cookie": login.headers["set-cookie"].split(";", 1)[0]}

        def create(payload):
            with httpx.Client(base_url=BASE, headers=headers, timeout=30) as caller:
                return caller.post("/sessions", json=payload)

        for group in range(30):
            sid = f"race-http-{uuid4()}"
            now = datetime.now(UTC)
            payload = {"schema_version": "1.0", "event_id": str(uuid4()), "session_id": sid,
                       "event_time": (now - timedelta(minutes=1)).isoformat(), "ingested_at": now.isoformat(),
                       "source": "synthetic_test", "producer_version": "1.0", "idempotency_key": str(uuid4()),
                       "event_type": "session.started", "sequence": 1, "session_kind": "study",
                       "privacy_mode": "behavioral"}
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                responses = list(pool.map(create, [payload] * 3))
            assert sorted(response.status_code for response in responses) == [200, 200, 201], (
                group, [(response.status_code, response.text) for response in responses])
            assert {response.json()["session_id"] for response in responses} == {sid}
            assert {response.json()["event_id"] for response in responses} == {payload["event_id"]}
            with httpx.Client(base_url=BASE, headers=headers, timeout=30) as reader:
                timeline = reader.get(f"/sessions/{sid}/timeline")
            assert timeline.status_code == 200 and timeline.json()["total"] == 1
            assert timeline.json()["items"][0]["event_id"] == payload["event_id"]
    print("PASS: 30 local HTTP groups; each 201/200/200, one session and one timeline event")


if __name__ == "__main__":
    main()
