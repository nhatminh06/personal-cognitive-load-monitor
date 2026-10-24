# Bronze storage

MinIO runs only under the `lake` profile. Credentials come from `.env.module2` or the environment; `.env.module2` is ignored and only a placeholder example is committed. An initializer idempotently creates `cogniflow-bronze` and `cogniflow-lakehouse`.

Bronze objects are immutable newline-delimited JSON batches:

```text
session_events/schema_version=1.0/event_date=YYYY-MM-DD/batch=<event-id-set-sha256>.jsonl
```

Each row preserves the complete validated source envelope and Kafka topic, partition and offset. Batch identity is deterministic, so replay reuses the same key and verifies its SHA-256 metadata. A conflicting checksum or unavailable store fails explicitly. Production consumers commit Kafka offsets only after `write_batch` returns; therefore the path is at least once and duplicate-safe, not exactly once.

The writer accepts multiple same-version/same-day events per object to avoid a permanent tiny-file-per-event design. Tiny integration tests may use a one-record batch.
