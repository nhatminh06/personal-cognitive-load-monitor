"""Local focus-session API and SQLite persistence regressions."""

from __future__ import annotations

import sqlite3
import hashlib
import asyncio
import multiprocessing
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import httpx

from cogniflow_sessions import ConflictError, FocusSessionRepository
from preprocessing_api.main import app
from preprocessing_api.sessions import get_session_repository

START = datetime.now(UTC) - timedelta(hours=1)
HEADERS = {"x-api-key": "session-secret"}


def _transition_process(path: str, payload: dict, owner: str, connection) -> None:
    from cogniflow_contracts import SessionLifecycleEvent

    try:
        FocusSessionRepository(path).transition(SessionLifecycleEvent.model_validate(payload), owner)
        connection.send("ok")
    except ConflictError:
        connection.send("conflict")
    finally:
        connection.close()


def lifecycle(session_id: str, kind: str, sequence: int, when: datetime, **changes):
    payload = {
        "event_id": str(uuid4()), "session_id": session_id, "event_time": when.isoformat(),
        "ingested_at": (when + timedelta(seconds=1)).isoformat(), "source": "local_api",
        "producer_version": "1.0.0", "idempotency_key": f"{session_id}:{sequence}",
        "event_type": f"session.{kind}", "sequence": sequence,
        "session_kind": "programming", "privacy_mode": "behavioral",
    }
    payload.update(changes)
    return payload


@pytest.fixture
def session_client(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIFLOW_API_KEY", "session-secret")
    repository = FocusSessionRepository(tmp_path / "sessions.sqlite3")
    async def repository_dependency():
        return repository

    app.dependency_overrides[get_session_repository] = repository_dependency
    class Client:
        def request(self, method, path, **kwargs):
            async def send():
                transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    return await client.request(method, path, **kwargs)
            return asyncio.run(send())

        def get(self, path, **kwargs):
            return self.request("GET", path, **kwargs)

        def post(self, path, **kwargs):
            return self.request("POST", path, **kwargs)

    yield Client(), repository
    app.dependency_overrides.clear()


def test_auth_creation_restart_and_privacy(session_client, monkeypatch):
    client, repository = session_client
    started = lifecycle("s-auth", "started", 1, START)
    assert client.post("/sessions", json=started).status_code == 401
    response = client.post("/sessions", json=started, headers=HEADERS)
    assert response.status_code == 201
    assert client.post("/sessions", json=started, headers=HEADERS).status_code == 200
    assert client.get("/sessions/s-auth").status_code == 401
    assert FocusSessionRepository(repository.path).session(
        "s-auth", hashlib.sha256(b"session-secret").hexdigest()
    )["state"] == "session.started"

    with sqlite3.connect(repository.path) as connection:
        connection.execute("UPDATE sessions SET owner_id='another-owner' WHERE session_id='s-auth'")
    assert client.get("/sessions/s-auth", headers=HEADERS).status_code == 404


def test_lifecycle_windows_labels_corrections_and_timeline(session_client):
    client, _ = session_client
    session_id = "s-flow"
    assert client.post("/sessions", json=lifecycle(session_id, "started", 1, START),
                       headers=HEADERS).status_code == 201
    paused = lifecycle(session_id, "paused", 2, START + timedelta(minutes=6))
    assert client.post(f"/sessions/{session_id}/transitions", json=paused,
                       headers=HEADERS).status_code == 200
    resumed = lifecycle(session_id, "resumed", 3, START + timedelta(minutes=7))
    assert client.post(f"/sessions/{session_id}/transitions", json=resumed,
                       headers=HEADERS).status_code == 200
    completed = lifecycle(session_id, "completed", 4, START + timedelta(minutes=12))
    assert client.post(f"/sessions/{session_id}/transitions", json=completed,
                       headers=HEADERS).status_code == 200

    state = client.get(f"/sessions/{session_id}", headers=HEADERS).json()
    assert state["state"] == "session.completed"
    assert len(state["completed_windows"]) == 2
    window = state["completed_windows"][0]
    reported = START + timedelta(minutes=20)
    label = {
        "event_id": str(uuid4()), "label_id": str(uuid4()), "session_id": session_id,
        "event_time": reported.isoformat(), "ingested_at": reported.isoformat(),
        "source": "local_api", "producer_version": "1.0.0",
        "idempotency_key": f"{session_id}:label:1", "event_type": "effort.reported",
        **window, "feature_cutoff": window["window_end"], "effort_rating": 6,
        "reported_at": reported.isoformat(), "label_source": "user_self_report",
    }
    response = client.post(f"/sessions/{session_id}/labels", json=label, headers=HEADERS)
    assert response.status_code == 201
    assert response.json()["compatibility_band"] == "HIGH"
    assert client.post(f"/sessions/{session_id}/labels", json=label,
                       headers=HEADERS).status_code == 200

    correction = {**label, "event_id": str(uuid4()), "label_id": str(uuid4()),
                  "idempotency_key": f"{session_id}:label:2", "effort_rating": 4,
                  "supersedes_label_id": label["label_id"],
                  "reported_at": (reported + timedelta(minutes=1)).isoformat(),
                  "event_time": (reported + timedelta(minutes=1)).isoformat(),
                  "ingested_at": (reported + timedelta(minutes=1)).isoformat()}
    assert client.post(f"/sessions/{session_id}/labels", json=correction,
                       headers=HEADERS).status_code == 201
    page = client.get(f"/sessions/{session_id}/timeline?limit=2&offset=1",
                      headers=HEADERS).json()
    assert len(page["items"]) == 2 and page["total"] == 8
    assert all("owner_id" not in item for item in page["items"])


def test_rejects_illegal_order_identity_and_incomplete_window(session_client):
    client, _ = session_client
    session_id = "s-errors"
    started = lifecycle(session_id, "started", 1, START)
    assert client.post("/sessions", json=started, headers=HEADERS).status_code == 201
    out_of_order = lifecycle(session_id, "paused", 3, START + timedelta(minutes=1))
    assert client.post(f"/sessions/{session_id}/transitions", json=out_of_order,
                       headers=HEADERS).status_code == 409
    duplicate_id = lifecycle(session_id, "paused", 2, START + timedelta(minutes=1),
                             event_id=started["event_id"])
    assert client.post(f"/sessions/{session_id}/transitions", json=duplicate_id,
                       headers=HEADERS).status_code == 409
    cancel = lifecycle(session_id, "cancelled", 2, START + timedelta(minutes=1))
    assert client.post(f"/sessions/{session_id}/transitions", json=cancel,
                       headers=HEADERS).status_code == 200
    after_terminal = lifecycle(session_id, "resumed", 3, START + timedelta(minutes=2))
    assert client.post(f"/sessions/{session_id}/transitions", json=after_terminal,
                       headers=HEADERS).status_code == 409

    reported = START + timedelta(minutes=10)
    incomplete = {
        "event_id": str(uuid4()), "label_id": str(uuid4()), "session_id": session_id,
        "event_time": reported.isoformat(), "ingested_at": reported.isoformat(),
        "source": "local_api", "producer_version": "1.0.0", "idempotency_key": "missing:1",
        "event_type": "effort.reported", "window_id": str(uuid4()),
        "window_start": START.isoformat(), "window_end": (START + timedelta(minutes=5)).isoformat(),
        "feature_cutoff": (START + timedelta(minutes=5)).isoformat(), "effort_rating": 8,
        "reported_at": reported.isoformat(), "label_source": "user_self_report",
    }
    assert client.post(f"/sessions/{session_id}/labels", json=incomplete,
                       headers=HEADERS).status_code == 422
    incomplete["effort_rating"] = 5
    assert client.post(f"/sessions/{session_id}/labels", json=incomplete,
                       headers=HEADERS).status_code == 409


def test_concurrent_transition_has_one_winner_and_rolls_back(tmp_path):
    from cogniflow_contracts import SessionLifecycleEvent

    repository = FocusSessionRepository(tmp_path / "concurrent.sqlite3")
    owner = "owner"
    started = SessionLifecycleEvent.model_validate(lifecycle("s-race", "started", 1, START))
    repository.create(started, owner)
    candidates = [SessionLifecycleEvent.model_validate(
        lifecycle("s-race", kind, 2, START + timedelta(minutes=1),
                  idempotency_key=f"race:{kind}")) for kind in ("paused", "cancelled")]

    context = multiprocessing.get_context("fork")
    readers, processes = [], []
    for event in candidates:
        reader, writer = context.Pipe(duplex=False)
        process = context.Process(
            target=_transition_process,
            args=(str(repository.path), event.model_dump(mode="json"), owner, writer),
        )
        readers.append(reader)
        processes.append(process)
        process.start()
        writer.close()
    results = [reader.recv() for reader in readers]
    for process in processes:
        process.join(5)
        assert process.exitcode == 0
    assert sorted(results) == ["conflict", "ok"]
    with sqlite3.connect(repository.path) as connection:
        assert connection.execute("SELECT count(*) FROM lifecycle_events").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM outbox").fetchone()[0] == 2
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [
            (1,), (2,), (3,)
        ]
