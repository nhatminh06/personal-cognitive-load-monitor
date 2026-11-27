-- Disposable synthetic D1 only; not a production migration.
CREATE TABLE gateway_nonces (nonce TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);
CREATE TABLE gateway_receipts (event_id TEXT PRIMARY KEY, digest TEXT NOT NULL);
