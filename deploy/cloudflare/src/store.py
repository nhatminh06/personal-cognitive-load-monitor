"""D1 persistence; all multi-statement mutations use atomic batches and version guards."""

import json
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from cogniflow_contracts import effort_band

NEXT = {
    "session.started": {"session.paused", "session.completed", "session.cancelled"},
    "session.resumed": {"session.paused", "session.completed", "session.cancelled"},
    "session.paused": {"session.resumed", "session.completed", "session.cancelled"},
}


class Store:
    def __init__(self, db):
        self.db = db
        self.rows_read = 0
        self.rows_written = 0

    def statement(self, sql, *args):
        return self.db.prepare(sql).bind(*args)

    async def batch(self, statements):
        # The pinned Workers SDK converts Python lists and binding wrappers for RPC.
        results = await self.db.batch(statements)
        for result in results:
            if not result.get("success", False):
                raise RuntimeError("D1 query failed")
            self.rows_read += result.get("meta", {}).get("rows_read", 0)
            self.rows_written += result.get("meta", {}).get("rows_written", 0)
        return results

    async def query(self, sql, *args):
        return (await self.batch([self.statement(sql, *args)]))[0].get("results", [])

    async def owned(self, sid, owner):
        rows = await self.query("SELECT * FROM sessions WHERE session_id=? AND owner_id=?", sid, owner)
        if not rows:
            raise HTTPException(404, "Session not found")
        return rows[0]

    async def existing(self, event, owner):
        rows = await self.query(
            "SELECT e.event_json,s.owner_id FROM events e JOIN sessions s USING(session_id) "
            "WHERE e.event_id=? OR e.idempotency_key=?", str(event.event_id), event.idempotency_key,
        )
        if not rows:
            return None
        requested = event.model_dump(mode="json")
        requested.pop("ingested_at")
        for row in rows:
            stored = json.loads(row["event_json"])
            comparable = dict(stored)
            comparable.pop("ingested_at")
            if row["owner_id"] != owner or comparable != requested:
                raise HTTPException(409, "Event identity or idempotency key is already in use")
        return stored

    def guard(self, session):
        return [
            self.statement("UPDATE sessions SET version=version+1 WHERE session_id=? AND version=?",
                           session["session_id"], session["version"]),
            self.statement("INSERT INTO cas_guard VALUES (changes())"),
            self.statement("DELETE FROM cas_guard"),
        ]

    def insert_event(self, event):
        return self.statement(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)",
            str(event.event_id), event.idempotency_key, event.session_id, event.event_type,
            event.event_time.isoformat(), getattr(event, "sequence", 0), event.model_dump_json(),
            str(event.label_id) if hasattr(event, "label_id") else None,
            str(event.window_id) if hasattr(event, "window_id") else None,
            event.reported_at.isoformat() if hasattr(event, "reported_at") else None,
        )

    def materialize(self, session, until):
        windows = []
        if session["state"] in {"session.started", "session.resumed"}:
            start = datetime.fromisoformat(session["last_event_time"])
            while start + timedelta(minutes=5) <= until:
                end = start + timedelta(minutes=5)
                wid = str(uuid5(NAMESPACE_URL, f"cogniflow:{session['session_id']}:{start.isoformat()}:{end.isoformat()}"))
                windows.append({"id": wid, "start": start.isoformat(), "end": end.isoformat()})
                start = end
        return self.statement(
            "INSERT OR IGNORE INTO windows SELECT json_extract(value,'$.id'),?,"
            "json_extract(value,'$.start'),json_extract(value,'$.end') FROM json_each(?)",
            session["session_id"], json.dumps(windows),
        )

    async def mutate(self, operation, event, owner):
        # Retry a losing CAS against fresh state, also resolving simultaneous identical retries.
        for attempt in range(3):
            if operation != "create":
                session = await self.owned(event.session_id, owner)
            existing = await self.existing(event, owner)
            if existing:
                if operation == "labels":
                    existing["compatibility_band"] = effort_band(event.effort_rating).value
                return existing, False
            if operation == "create":
                if event.event_type != "session.started" or event.sequence != 1:
                    raise HTTPException(409, "Session must begin with sequence 1 session.started")
                if await self.query("SELECT 1 FROM sessions WHERE session_id=?", event.session_id):
                    raise HTTPException(409, "Session already exists")
                statements = [self.statement(
                    "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,0)", event.session_id, owner,
                    event.session_kind, event.privacy_mode, event.planned_duration_seconds,
                    event.event_type, event.sequence, event.event_time.isoformat(), event.ingested_at.isoformat(),
                )]
            else:
                statements = self.guard(session)
                if operation == "transitions":
                    if event.event_type not in NEXT.get(session["state"], set()):
                        raise HTTPException(409, "Illegal lifecycle transition")
                    if event.sequence != session["last_sequence"] + 1:
                        raise HTTPException(409, "Lifecycle sequence must be contiguous")
                    if event.event_time < datetime.fromisoformat(session["last_event_time"]):
                        raise HTTPException(409, "Lifecycle event_time cannot move backwards")
                    if (event.session_kind, event.privacy_mode, event.planned_duration_seconds) != (
                        session["session_kind"], session["privacy_mode"], session["planned_duration_seconds"]
                    ):
                        raise HTTPException(409, "Session lifecycle metadata cannot change")
                    statements += [self.materialize(session, event.event_time), self.statement(
                        "UPDATE sessions SET state=?,last_sequence=?,last_event_time=? WHERE session_id=?",
                        event.event_type, event.sequence, event.event_time.isoformat(), event.session_id,
                    )]
                else:
                    windows = await self.query(
                        "SELECT * FROM windows WHERE window_id=? AND session_id=?",
                        str(event.window_id), event.session_id,
                    )
                    if not windows or (event.window_start.isoformat(), event.window_end.isoformat()) != (
                        windows[0]["window_start"], windows[0]["window_end"]
                    ):
                        raise HTTPException(409, "Event must reference a completed session window")
                    if operation == "labels":
                        latest = await self.query(
                            "SELECT label_id FROM events WHERE window_id=? AND label_id IS NOT NULL "
                            "ORDER BY reported_at DESC,rowid DESC LIMIT 1", str(event.window_id),
                        )
                        expected = latest[0]["label_id"] if latest else None
                        if (str(event.supersedes_label_id) if event.supersedes_label_id else None) != expected:
                            raise HTTPException(409, "Correction must supersede the latest label for the window")
            statements.append(self.insert_event(event))
            try:
                await self.batch(statements)
            except Exception as exc:
                message = str(exc).lower()
                if any(term in message for term in ("cas_guard", "unique constraint")):
                    if attempt < 2:
                        continue
                    raise HTTPException(409, "Concurrent write conflicts with persisted state") from exc
                raise
            result = event.model_dump(mode="json")
            if operation == "labels":
                result["compatibility_band"] = effort_band(event.effort_rating).value
            return result, True
        raise HTTPException(409, "Concurrent write conflicts with persisted state")

    async def session(self, sid, owner):
        results = await self.batch([
            self.statement("SELECT * FROM sessions WHERE session_id=? AND owner_id=?", sid, owner),
            self.statement("SELECT window_id,window_start,window_end FROM windows WHERE session_id=? ORDER BY window_start", sid),
            self.statement("SELECT event_type,event_time FROM events WHERE session_id=? AND sequence>0 ORDER BY sequence", sid),
        ])
        if not results[0]["results"]:
            raise HTTPException(404, "Session not found")
        row = results[0]["results"][0]
        active = None
        seconds = 0
        for event in results[2]["results"]:
            when = datetime.fromisoformat(event["event_time"])
            if event["event_type"] in {"session.started", "session.resumed"}:
                active = when
            elif active is not None:
                seconds += max(0, int((when - active).total_seconds()))
                active = None
        return {**{key: row[key] for key in (
            "session_id", "session_kind", "privacy_mode", "planned_duration_seconds",
            "state", "last_sequence", "last_event_time",
        )}, "confirmed_active_seconds": seconds, "completed_windows": results[1]["results"]}

    async def refresh(self, sid, owner):
        for attempt in range(3):
            row = await self.owned(sid, owner)
            try:
                await self.batch([*self.guard(row), self.materialize(row, datetime.now(UTC))])
                return await self.session(sid, owner)
            except Exception as exc:
                if "cas_guard" not in str(exc).lower():
                    raise
                if attempt == 2:
                    raise HTTPException(409, "Concurrent window refresh; retry") from exc

    async def timeline(self, sid, owner, limit, offset):
        await self.owned(sid, owner)
        union = (
            "SELECT event_json,event_time,sequence FROM events WHERE session_id=? UNION ALL "
            "SELECT json_object('event_type','window.completed','window_id',window_id,"
            "'window_start',window_start,'window_end',window_end,'event_time',window_end),"
            "window_end,0 FROM windows WHERE session_id=?"
        )
        results = await self.batch([
            self.statement(f"SELECT event_json FROM ({union}) ORDER BY event_time,sequence LIMIT ? OFFSET ?", sid, sid, limit, offset),
            self.statement(f"SELECT count(*) AS total FROM ({union})", sid, sid),
        ])
        return {"items": [json.loads(r["event_json"]) for r in results[0]["results"]],
                "total": results[1]["results"][0]["total"], "limit": limit, "offset": offset}
