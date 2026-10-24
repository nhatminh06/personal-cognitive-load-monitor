# Kafka ingestion

Kafka 3.9.2 runs as one KRaft combined broker/controller for local development only. Three topics have three partitions and replication factor one:

- `cogniflow.session-events.v1`
- `cogniflow.features.v1`
- `cogniflow.dead-letter.v1`

The session ID is the partition key, preserving ordering within a session. The producer uses `acks=all`, idempotence, five bounded retries and bounded request/delivery timeouts. `/events` returns 202 only after the delivery callback and flush succeed; unavailable Kafka returns 503. Optional local API-key authorization uses `EVENT_API_KEY` and `X-API-Key`.

Consumers disable auto-commit. A valid offset is synchronously committed after the handler succeeds. An invalid record is committed only after the dead-letter producer flushes successfully. A bounded in-process UUID cache suppresses duplicates during one process lifetime; committed consumer-group offsets provide restart position. These mechanics provide at-least-once delivery, not end-to-end exactly once.

Runtime evidence on 2026-10-23: event `6e80e547-7c70-400f-87e7-0e455ac3c62a` was published and consumed from `cogniflow.session-events.v1`. Kafka used about 290 MiB of its 768 MiB limit. Stop it without deleting the volume:

```bash
docker compose -f infra/module2/docker-compose.yml --profile ingestion down
```
