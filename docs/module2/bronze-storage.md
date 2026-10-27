# Bronze storage

SeaweedFS provides the S3-compatible endpoint under the `lake` profile. Credentials come from `.env.module2` or the environment; `.env.module2` is ignored and only a placeholder example is committed. An initializer idempotently creates `cogniflow-bronze` and `cogniflow-lakehouse`. The Compose service name remains `minio` solely to preserve existing internal endpoint contracts.

## Instructor MinIO criterion

SeaweedFS compatibility is not claimed as MinIO product credit. A grading-only
MinIO profile was evaluated and rejected on 2026-10-27: MinIO's upstream OSS
repository is archived and explicitly no longer maintained, legacy binaries no
longer receive fixes, and supported AIStor requires a separate license. Recent
upstream advisories include unauthenticated-write and denial-of-service issues.
Introducing a frozen legacy image would violate this repository's security gate
and SEC-022-style local-only discipline.

Primary evidence: the [upstream repository](https://github.com/minio/minio)
states that it is archived/no longer maintained and that legacy binaries do not
receive updates; the [upstream advisory list](https://github.com/minio/minio/security/advisories)
contains the recent security findings; and MinIO's
[licensing page](https://www.min.io/pricing) distinguishes the maintained,
commercially licensed AIStor line from the discontinued OSS codebase.

The instructor must therefore approve one of these paths before MinIO credit is
claimed: accept the already runtime-verified SeaweedFS S3 implementation as an
equivalent, provide an authorized AIStor license/image for an isolated grading
run, or waive the exact-product criterion. No existing SeaweedFS volume will be
migrated or destroyed for that decision.

Bronze objects are immutable newline-delimited JSON batches:

```text
session_events/schema_version=1.0/event_date=YYYY-MM-DD/batch=<event-id-set-sha256>.jsonl
```

Each row preserves the complete validated source envelope and Kafka topic, partition and offset. Batch identity is deterministic, so replay reuses the same key and verifies its SHA-256 metadata. A conflicting checksum or unavailable store fails explicitly. Production consumers commit Kafka offsets only after `write_batch` returns; therefore the path is at least once and duplicate-safe, not exactly once.

The writer accepts multiple same-version/same-day events per object to avoid a permanent tiny-file-per-event design. Tiny integration tests may use a one-record batch.
