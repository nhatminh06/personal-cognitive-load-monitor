"""Fast parity tests use SQLite only as a D1 binding double; not runtime qualification."""

import asyncio
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "src"))
from store import Store  # noqa: E402
from cogniflow_contracts import EffortLabelEvent, SessionLifecycleEvent  # noqa: E402
from cogniflow_sessions import FocusSessionRepository  # noqa: E402


class Statement:
    def __init__(self, sql):
        self.sql, self.args = sql, ()

    def bind(self, *args):
        self.args = args
        return self


class DB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript((HERE / "migrations/0001_focus.sql").read_text())

    def prepare(self, sql):
        return Statement(sql)

    async def batch(self, statements):
        # Yield to expose read/validate/write races between coroutines.
        await asyncio.sleep(0)
        try:
            self.conn.execute("BEGIN")
            results = []
            for stmt in statements:
                cursor = self.conn.execute(stmt.sql, stmt.args)
                results.append({"success": True, "results": [dict(r) for r in cursor.fetchall()]})
            self.conn.commit()
            return results
        except Exception:
            self.conn.rollback()
            raise


def event(sid="synthetic", sequence=1, kind="session.started", when=None):
    return SessionLifecycleEvent(
        event_id=uuid4(), session_id=sid, sequence=sequence, event_type=kind,
        event_time=when or datetime.now(UTC) - timedelta(minutes=10), ingested_at=datetime.now(UTC),
        source="synthetic_test", producer_version="1.0", idempotency_key=str(uuid4()),
        session_kind="study", privacy_mode="behavioral",
    )


def test_linux_contract_parity(tmp_path):
    async def check():
        d1 = Store(DB())
        linux = FocusSessionRepository(tmp_path / "synthetic.sqlite")
        start = event()
        stop = event(sequence=2, kind="session.completed", when=start.event_time + timedelta(minutes=6))
        for operation, item in [("create", start), ("transitions", stop)]:
            expected = linux.create(item, "owner") if operation == "create" else linux.transition(item, "owner")
            assert await d1.mutate(operation, item, "owner") == expected
            assert await d1.mutate(operation, item, "owner") == (expected[0], False)
        assert await d1.session(start.session_id, "owner") == linux.session(start.session_id, "owner")
        window = (await d1.session(start.session_id, "owner"))["completed_windows"][0]
        now = datetime.now(UTC)
        label = EffortLabelEvent(
            session_id=start.session_id, window_id=window["window_id"],
            window_start=window["window_start"], window_end=window["window_end"],
            feature_cutoff=window["window_end"], event_time=now, reported_at=now, ingested_at=now,
            source="synthetic_test", producer_version="1.0", idempotency_key=str(uuid4()), effort_rating=6,
        )
        assert await d1.mutate("labels", label, "owner") == linux.add_label(label, "owner")
        expected = linux.timeline(start.session_id, "owner", 50, 0)
        assert await d1.timeline(start.session_id, "owner", 50, 0) == expected
        for operation in (lambda: d1.session(start.session_id, "other"),
                          lambda: d1.mutate("create", start, "other")):
            with pytest.raises(HTTPException):
                await operation()
    asyncio.run(check())


def test_atomic_guard_and_concurrent_retries():
    async def check():
        db = DB()
        repo = Store(db)
        start = event()
        results = await asyncio.gather(*(repo.mutate("create", start, "owner") for _ in range(3)))
        assert sum(created for _, created in results) == 1
        stop = event(sequence=2, kind="session.completed", when=start.event_time + timedelta(minutes=6))
        pause = event(sequence=2, kind="session.paused", when=stop.event_time)
        outcomes = await asyncio.gather(repo.mutate("transitions", stop, "owner"),
                                        repo.mutate("transitions", pause, "owner"), return_exceptions=True)
        assert sum(isinstance(r, HTTPException) for r in outcomes) == 1
        assert (await repo.timeline(start.session_id, "owner", 100, 0))["total"] == 3
        stale = {**await repo.owned(start.session_id, "owner"), "version": -1}
        with pytest.raises(sqlite3.IntegrityError):
            await repo.batch([*repo.guard(stale), repo.statement("DELETE FROM events")])
        assert len(await repo.query("SELECT * FROM events")) == 2
    asyncio.run(check())
