"""Offline checks for the live PR 3 Kafka smoke harness."""

import asyncio

import pytest

from cogniflow_sessions import FocusSessionRepository
from scripts.smoke_focus_kafka import _api_setup, _verify_pending, run
from scripts.smoke_flink_redis import _prepare


def test_smoke_harness_uses_authenticated_api_and_creates_one_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIFLOW_API_KEY", "offline-secret")
    repository = FocusSessionRepository(tmp_path / "smoke.sqlite3")
    session_id, event_id = asyncio.run(_api_setup(repository, "offline-secret"))
    assert _verify_pending(repository, session_id, event_id) == 3
    assert sum(row["event_id"] == event_id for row in repository.pending_outbox(100)) == 1


def test_smoke_harness_refuses_reused_database(tmp_path, monkeypatch):
    database = tmp_path / "existing.sqlite3"
    database.touch()
    monkeypatch.setenv("COGNIFLOW_API_KEY", "secret")
    with pytest.raises(RuntimeError, match="fresh path"):
        run(database, "unused")


def test_flink_smoke_fixture_uses_two_real_completed_windows(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIFLOW_API_KEY", "offline-secret")
    repository = FocusSessionRepository(tmp_path / "flink.sqlite3")
    session_id, older, newer = asyncio.run(_prepare(repository, "offline-secret"))
    assert older["session_id"] == newer["session_id"] == session_id
    assert older["window_end"] < newer["window_end"]
    assert newer["build_count"] is newer["test_count"] is None
    assert len(repository.pending_outbox(100)) == 3
