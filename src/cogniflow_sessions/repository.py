"""SQLite repository for ordered, append-only focus-session events."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from cogniflow_contracts import (
    BehavioralActivityEvent,
    CvFeatureWindowEvent,
    EffortLabelEvent,
    SessionLifecycleEvent,
    effort_band,
)

_MIGRATIONS = (
    """
    CREATE TABLE sessions (
      session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, session_kind TEXT NOT NULL,
      privacy_mode TEXT NOT NULL, planned_duration_seconds INTEGER, state TEXT NOT NULL,
      last_sequence INTEGER NOT NULL, last_event_time TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE lifecycle_events (
      event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
      idempotency_key TEXT NOT NULL UNIQUE, sequence INTEGER NOT NULL,
      event_type TEXT NOT NULL, event_time TEXT NOT NULL, event_json TEXT NOT NULL,
      UNIQUE(session_id, sequence)
    );
    CREATE TABLE windows (
      window_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
      window_start TEXT NOT NULL, window_end TEXT NOT NULL,
      UNIQUE(session_id, window_start, window_end)
    );
    CREATE TABLE effort_labels (
      label_id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
      session_id TEXT NOT NULL REFERENCES sessions(session_id),
      window_id TEXT NOT NULL REFERENCES windows(window_id), idempotency_key TEXT NOT NULL UNIQUE,
      supersedes_label_id TEXT REFERENCES effort_labels(label_id), reported_at TEXT NOT NULL,
      effort_rating INTEGER NOT NULL CHECK(effort_rating BETWEEN 1 AND 7), event_json TEXT NOT NULL
    );
    CREATE TABLE outbox (
      event_id TEXT PRIMARY KEY, topic TEXT NOT NULL, event_json TEXT NOT NULL,
      created_at TEXT NOT NULL, published_at TEXT
    );
    CREATE INDEX lifecycle_timeline ON lifecycle_events(session_id, event_time, sequence);
    CREATE INDEX labels_timeline ON effort_labels(session_id, reported_at);
    """,
    """
    CREATE TABLE activity_events (
      event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
      window_id TEXT NOT NULL UNIQUE REFERENCES windows(window_id),
      idempotency_key TEXT NOT NULL UNIQUE, event_time TEXT NOT NULL, event_json TEXT NOT NULL
    );
    ALTER TABLE outbox ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE outbox ADD COLUMN last_attempt_at TEXT;
    CREATE INDEX activity_timeline ON activity_events(session_id, event_time);
    """,
    """
    CREATE TABLE cv_events (
      event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
      window_id TEXT NOT NULL UNIQUE REFERENCES windows(window_id),
      idempotency_key TEXT NOT NULL UNIQUE, event_time TEXT NOT NULL, event_json TEXT NOT NULL
    );
    CREATE INDEX cv_timeline ON cv_events(session_id, event_time);
    """,
)

_NEXT = {
    "session.started": {"session.paused", "session.completed", "session.cancelled"},
    "session.paused": {"session.resumed", "session.completed", "session.cancelled"},
    "session.resumed": {"session.paused", "session.completed", "session.cancelled"},
}
_lock = threading.RLock()


class ConflictError(ValueError):
    """The request conflicts with persisted session state."""


class NotFoundError(ValueError):
    """The session is absent or belongs to another owner."""


class FocusSessionRepository:
    def __init__(self, path: str | Path | None = None):
        configured_path = path if path is not None else os.environ.get(
            "FOCUS_SESSION_STORE_PATH", "data/focus-sessions.sqlite3"
        )
        self.path = Path(configured_path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            self._migrate(connection)
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for version, sql in enumerate(_MIGRATIONS, 1):
            if version in applied:
                continue
            try:
                connection.executescript(
                    f"BEGIN IMMEDIATE;\n{sql}\n"
                    f"INSERT INTO schema_migrations VALUES ({version}, datetime('now'));\n"
                    "COMMIT;"
                )
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with _lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _json(
        event: SessionLifecycleEvent | EffortLabelEvent | BehavioralActivityEvent | CvFeatureWindowEvent,
    ) -> str:
        return event.model_dump_json()

    @staticmethod
    def _owned_session(connection: sqlite3.Connection, session_id: str, owner: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id=? AND owner_id=?", (session_id, owner)
        ).fetchone()
        if row is None:
            raise NotFoundError("Session not found")
        return row

    @staticmethod
    def _existing(connection: sqlite3.Connection, event_id: UUID, key: str) -> str | None:
        row = connection.execute(
            "SELECT event_json FROM lifecycle_events WHERE event_id=? OR idempotency_key=? "
            "UNION ALL SELECT event_json FROM effort_labels WHERE event_id=? OR idempotency_key=? "
            "UNION ALL SELECT event_json FROM activity_events WHERE event_id=? OR idempotency_key=? "
            "UNION ALL SELECT event_json FROM cv_events WHERE event_id=? OR idempotency_key=? "
            "LIMIT 1",
            (str(event_id), key, str(event_id), key, str(event_id), key, str(event_id), key),
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _same_request(existing: str, requested: str) -> bool:
        left, right = json.loads(existing), json.loads(requested)
        left.pop("ingested_at", None)
        right.pop("ingested_at", None)
        return left == right

    def create(self, event: SessionLifecycleEvent, owner: str) -> tuple[dict[str, Any], bool]:
        serialized = self._json(event)
        with self._write() as connection:
            existing = self._existing(connection, event.event_id, event.idempotency_key)
            if existing is not None:
                if self._same_request(existing, serialized):
                    return json.loads(existing), False
                raise ConflictError("Event identity or idempotency key is already in use")
            if event.event_type != "session.started" or event.sequence != 1:
                raise ConflictError("Session must begin with sequence 1 session.started")
            if connection.execute(
                "SELECT 1 FROM sessions WHERE session_id=?", (event.session_id,)
            ).fetchone():
                raise ConflictError("Session already exists")
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.session_id, owner, event.session_kind, event.privacy_mode,
                 event.planned_duration_seconds, event.event_type, event.sequence,
                 event.event_time.isoformat(), event.ingested_at.isoformat()),
            )
            self._insert_lifecycle(connection, event, serialized)
        return json.loads(serialized), True

    @staticmethod
    def _insert_lifecycle(
        connection: sqlite3.Connection, event: SessionLifecycleEvent, serialized: str
    ) -> None:
        connection.execute(
            "INSERT INTO lifecycle_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(event.event_id), event.session_id, event.idempotency_key, event.sequence,
             event.event_type, event.event_time.isoformat(), serialized),
        )
        connection.execute(
            "INSERT INTO outbox(event_id, topic, event_json, created_at, published_at) "
            "VALUES (?, ?, ?, ?, NULL)",
            (str(event.event_id), "cogniflow.session-lifecycle.v1", serialized,
             datetime.now(UTC).isoformat()),
        )

    def transition(self, event: SessionLifecycleEvent, owner: str) -> tuple[dict[str, Any], bool]:
        serialized = self._json(event)
        with self._write() as connection:
            session = self._owned_session(connection, event.session_id, owner)
            existing = self._existing(connection, event.event_id, event.idempotency_key)
            if existing is not None:
                if self._same_request(existing, serialized):
                    return json.loads(existing), False
                raise ConflictError("Event identity or idempotency key is already in use")
            if event.event_type not in _NEXT.get(session["state"], set()):
                raise ConflictError("Illegal lifecycle transition")
            if event.sequence != session["last_sequence"] + 1:
                raise ConflictError("Lifecycle sequence must be contiguous")
            if event.event_time.isoformat() < session["last_event_time"]:
                raise ConflictError("Lifecycle event_time cannot move backwards")
            metadata = (event.session_kind, event.privacy_mode, event.planned_duration_seconds)
            if metadata != (session["session_kind"], session["privacy_mode"],
                            session["planned_duration_seconds"]):
                raise ConflictError("Session lifecycle metadata cannot change")
            self._materialize_windows(connection, event.session_id, session["state"],
                                      session["last_event_time"], event.event_time)
            self._insert_lifecycle(connection, event, serialized)
            connection.execute(
                "UPDATE sessions SET state=?, last_sequence=?, last_event_time=? WHERE session_id=?",
                (event.event_type, event.sequence, event.event_time.isoformat(), event.session_id),
            )
        return json.loads(serialized), True

    @staticmethod
    def _materialize_windows(
        connection: sqlite3.Connection, session_id: str, prior_state: str,
        segment_start: str, segment_end: datetime,
    ) -> None:
        if prior_state not in {"session.started", "session.resumed"}:
            return
        start = datetime.fromisoformat(segment_start)
        while start + timedelta(minutes=5) <= segment_end:
            end = start + timedelta(minutes=5)
            window_id = uuid5(NAMESPACE_URL, f"cogniflow:{session_id}:{start.isoformat()}:{end.isoformat()}")
            connection.execute(
                "INSERT OR IGNORE INTO windows VALUES (?, ?, ?, ?)",
                (str(window_id), session_id, start.isoformat(), end.isoformat()),
            )
            start = end

    def add_label(self, event: EffortLabelEvent, owner: str) -> tuple[dict[str, Any], bool]:
        serialized = self._json(event)
        with self._write() as connection:
            self._owned_session(connection, event.session_id, owner)
            existing = self._existing(connection, event.event_id, event.idempotency_key)
            if existing is not None:
                if self._same_request(existing, serialized):
                    result = json.loads(existing)
                    result["compatibility_band"] = effort_band(event.effort_rating).value
                    return result, False
                raise ConflictError("Event identity or idempotency key is already in use")
            window = connection.execute(
                "SELECT * FROM windows WHERE window_id=? AND session_id=?",
                (str(event.window_id), event.session_id),
            ).fetchone()
            if window is None or (event.window_start.isoformat(), event.window_end.isoformat()) != (
                window["window_start"], window["window_end"]
            ):
                raise ConflictError("Label must reference a completed session window")
            latest = connection.execute(
                "SELECT label_id FROM effort_labels WHERE window_id=? "
                "ORDER BY reported_at DESC, rowid DESC LIMIT 1", (str(event.window_id),)
            ).fetchone()
            expected = latest[0] if latest else None
            if (str(event.supersedes_label_id) if event.supersedes_label_id else None) != expected:
                raise ConflictError("Correction must supersede the latest label for the window")
            connection.execute(
                "INSERT INTO effort_labels VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(event.label_id), str(event.event_id), event.session_id, str(event.window_id),
                 event.idempotency_key, expected, event.reported_at.isoformat(),
                 event.effort_rating, serialized),
            )
            connection.execute(
                "INSERT INTO outbox(event_id, topic, event_json, created_at, published_at) "
                "VALUES (?, ?, ?, ?, NULL)",
                (str(event.event_id), "cogniflow.effort-labels.v1", serialized,
                 datetime.now(UTC).isoformat()),
            )
        result = json.loads(serialized)
        result["compatibility_band"] = effort_band(event.effort_rating).value
        return result, True

    def add_activity(
        self, event: BehavioralActivityEvent, owner: str
    ) -> tuple[dict[str, Any], bool]:
        serialized = self._json(event)
        with self._write() as connection:
            self._owned_session(connection, event.session_id, owner)
            existing = self._existing(connection, event.event_id, event.idempotency_key)
            if existing is not None:
                if self._same_request(existing, serialized):
                    return json.loads(existing), False
                raise ConflictError("Event identity or idempotency key is already in use")
            window = connection.execute(
                "SELECT window_start, window_end FROM windows WHERE window_id=? AND session_id=?",
                (str(event.window_id), event.session_id),
            ).fetchone()
            if window is None or (event.window_start.isoformat(), event.window_end.isoformat()) != (
                window["window_start"], window["window_end"]
            ):
                raise ConflictError("Activity must reference a completed session window")
            try:
                connection.execute(
                    "INSERT INTO activity_events VALUES (?, ?, ?, ?, ?, ?)",
                    (str(event.event_id), event.session_id, str(event.window_id),
                     event.idempotency_key, event.event_time.isoformat(), serialized),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("Window already has an activity event") from exc
            connection.execute(
                "INSERT INTO outbox(event_id, topic, event_json, created_at, published_at) "
                "VALUES (?, ?, ?, ?, NULL)",
                (str(event.event_id), "cogniflow.behavioral-activity.v1", serialized,
                 datetime.now(UTC).isoformat()),
            )
        return json.loads(serialized), True

    def add_cv(self, event: CvFeatureWindowEvent, owner: str) -> tuple[dict[str, Any], bool]:
        serialized = self._json(event)
        with self._write() as connection:
            session = self._owned_session(connection, event.session_id, owner)
            existing = self._existing(connection, event.event_id, event.idempotency_key)
            if existing is not None:
                if self._same_request(existing, serialized):
                    return json.loads(existing), False
                raise ConflictError("Event identity or idempotency key is already in use")
            if session["state"] in {"session.started", "session.resumed"}:
                self._materialize_windows(
                    connection, event.session_id, session["state"],
                    session["last_event_time"], min(event.window_end, datetime.now(UTC)),
                )
            window = connection.execute(
                "SELECT window_start, window_end FROM windows WHERE window_id=? AND session_id=?",
                (str(event.window_id), event.session_id),
            ).fetchone()
            if window is None or (event.window_start.isoformat(), event.window_end.isoformat()) != (
                window["window_start"], window["window_end"]
            ):
                raise ConflictError("CV event must reference a completed session window")
            try:
                connection.execute(
                    "INSERT INTO cv_events VALUES (?, ?, ?, ?, ?, ?)",
                    (str(event.event_id), event.session_id, str(event.window_id),
                     event.idempotency_key, event.event_time.isoformat(), serialized),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError("Window already has a CV event") from exc
        return json.loads(serialized), True

    def pending_outbox(self, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("outbox limit must be between 1 and 100")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT event_id, topic, event_json, attempts FROM outbox "
                "WHERE published_at IS NULL ORDER BY created_at, rowid LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_published(self, event_id: str, published_at: datetime) -> None:
        with self._write() as connection:
            updated = connection.execute(
                "UPDATE outbox SET published_at=? WHERE event_id=? AND published_at IS NULL",
                (published_at.isoformat(), event_id),
            ).rowcount
            if updated != 1:
                raise ConflictError("Outbox event is absent or already published")

    def mark_failed(self, event_id: str, attempted_at: datetime) -> None:
        with self._write() as connection:
            connection.execute(
                "UPDATE outbox SET attempts=attempts+1, last_attempt_at=? "
                "WHERE event_id=? AND published_at IS NULL",
                (attempted_at.isoformat(), event_id),
            )

    def session(self, session_id: str, owner: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = self._owned_session(connection, session_id, owner)
            windows = connection.execute(
                "SELECT window_id, window_start, window_end FROM windows WHERE session_id=? "
                "ORDER BY window_start", (session_id,)
            ).fetchall()
        return {
            "session_id": row["session_id"], "session_kind": row["session_kind"],
            "privacy_mode": row["privacy_mode"],
            "planned_duration_seconds": row["planned_duration_seconds"],
            "state": row["state"], "last_sequence": row["last_sequence"],
            "last_event_time": row["last_event_time"],
            "completed_windows": [dict(window) for window in windows],
        }

    def timeline(self, session_id: str, owner: str, limit: int, offset: int) -> dict[str, Any]:
        with self._connection() as connection:
            self._owned_session(connection, session_id, owner)
            lifecycle = [json.loads(row[0]) for row in connection.execute(
                "SELECT event_json FROM lifecycle_events WHERE session_id=?", (session_id,)
            )]
            windows = [{"event_type": "window.completed", **dict(row), "event_time": row["window_end"]}
                       for row in connection.execute(
                           "SELECT window_id, window_start, window_end FROM windows WHERE session_id=?",
                           (session_id,))]
            labels = [json.loads(row[0]) for row in connection.execute(
                "SELECT event_json FROM effort_labels WHERE session_id=?", (session_id,)
            )]
            activity = [json.loads(row[0]) for row in connection.execute(
                "SELECT event_json FROM activity_events WHERE session_id=?", (session_id,)
            )]
            cv = [json.loads(row[0]) for row in connection.execute(
                "SELECT event_json FROM cv_events WHERE session_id=?", (session_id,)
            )]
        events = sorted(lifecycle + windows + labels + activity + cv,
                        key=lambda item: (item["event_time"], item.get("sequence", 0)))
        return {"items": events[offset:offset + limit], "limit": limit, "offset": offset,
                "total": len(events)}

    def experiment_snapshot(self, owner: str, cutoff: datetime) -> dict[str, Any]:
        """Read one owner-scoped, point-in-time aggregate snapshot for local experiments."""

        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("snapshot cutoff must include a timezone")
        cutoff = cutoff.astimezone(UTC)
        with self._connection() as connection:
            connection.execute("BEGIN")
            sessions = connection.execute(
                "SELECT session_id, session_kind, privacy_mode, state, created_at "
                "FROM sessions WHERE owner_id=? AND state!='session.cancelled' "
                "ORDER BY created_at, session_id",
                (owner,),
            ).fetchall()
            session_ids = [row["session_id"] for row in sessions]
            if not session_ids:
                connection.commit()
                return {
                    "source": "sqlite://focus-session-store", "snapshot_cutoff": cutoff.isoformat(),
                    "sessions": [], "windows": [], "lifecycle": [], "activity": [],
                    "cv": [], "labels": [],
                }
            placeholders = ",".join("?" for _ in session_ids)
            windows = connection.execute(
                f"SELECT window_id, session_id, window_start, window_end FROM windows "
                f"WHERE session_id IN ({placeholders}) AND window_end<=? "
                "ORDER BY window_start, window_id",
                (*session_ids, cutoff.isoformat()),
            ).fetchall()

            def event_json(table: str, time_column: str) -> list[dict[str, Any]]:
                rows = connection.execute(
                    f"SELECT event_json FROM {table} WHERE session_id IN ({placeholders}) "
                    f"AND {time_column}<=? ORDER BY {time_column}, rowid",
                    (*session_ids, cutoff.isoformat()),
                ).fetchall()
                return [json.loads(row[0]) for row in rows]

            result = {
                "source": "sqlite://focus-session-store",
                "snapshot_cutoff": cutoff.isoformat(),
                "sessions": [dict(row) for row in sessions],
                "windows": [dict(row) for row in windows],
                "lifecycle": event_json("lifecycle_events", "event_time"),
                "activity": event_json("activity_events", "event_time"),
                "cv": event_json("cv_events", "event_time"),
                "labels": event_json("effort_labels", "reported_at"),
            }
            connection.commit()
        return result
