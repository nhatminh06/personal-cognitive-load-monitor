CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, session_kind TEXT NOT NULL,
  privacy_mode TEXT NOT NULL, planned_duration_seconds INTEGER, state TEXT NOT NULL,
  last_sequence INTEGER NOT NULL, last_event_time TEXT NOT NULL, created_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE events (
  event_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL REFERENCES sessions(session_id),
  event_type TEXT NOT NULL, event_time TEXT NOT NULL, sequence INTEGER NOT NULL DEFAULT 0,
  event_json TEXT NOT NULL, label_id TEXT UNIQUE, window_id TEXT,
  reported_at TEXT
);
CREATE UNIQUE INDEX lifecycle_sequence ON events(session_id, sequence) WHERE sequence > 0;
CREATE UNIQUE INDEX activity_window ON events(window_id) WHERE event_type='behavioral.window';
CREATE INDEX event_timeline ON events(session_id, event_time, sequence);
CREATE INDEX latest_label ON events(window_id, reported_at DESC) WHERE label_id IS NOT NULL;
CREATE TABLE windows (
  window_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
  window_start TEXT NOT NULL, window_end TEXT NOT NULL,
  UNIQUE(session_id, window_start, window_end)
);
CREATE INDEX window_timeline ON windows(session_id, window_end);
-- A failed compare-and-swap aborts the entire D1 batch, including subsequent inserts.
CREATE TABLE cas_guard (ok INTEGER NOT NULL CONSTRAINT cas_guard CHECK (ok=1));
CREATE TABLE browser_sessions (
  token_hash TEXT PRIMARY KEY, owner_id TEXT NOT NULL, expires_at INTEGER NOT NULL
);
CREATE INDEX browser_expiry ON browser_sessions(expires_at);
CREATE TABLE estimates (
  estimate_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, created_at TEXT NOT NULL,
  result_json TEXT NOT NULL
);
CREATE INDEX estimate_history ON estimates(owner_id, created_at);
