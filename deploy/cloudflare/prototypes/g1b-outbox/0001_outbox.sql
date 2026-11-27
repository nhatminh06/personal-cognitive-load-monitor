-- Disposable G1B test database only. Never apply to the deployed D1 database.
CREATE TABLE outbox (
  delivery_order INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id),
  session_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  owner_id TEXT NOT NULL,
  payload TEXT NOT NULL,
  digest TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('pending','leased','retry','acknowledged','dead')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at INTEGER NOT NULL DEFAULT 0,
  lease_token TEXT,
  lease_until INTEGER,
  acknowledged_at INTEGER,
  error_class TEXT,
  CHECK ((state='leased')=(lease_token IS NOT NULL))
);
CREATE INDEX outbox_due ON outbox(state, next_attempt_at, lease_until);
-- Match the production events.lifecycle_sequence predicate. Zero is not a position.
CREATE UNIQUE INDEX outbox_lifecycle_sequence ON outbox(session_id, sequence) WHERE sequence > 0;
CREATE INDEX outbox_session_order ON outbox(session_id, delivery_order);
