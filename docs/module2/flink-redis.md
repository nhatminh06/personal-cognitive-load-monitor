# Flink and Redis

The Flink 1.20.5 Java DataStream job consumes versioned session events with a two-minute out-of-order watermark. Per session it rejects duplicate IDs, events behind the watermark, and snapshots older than the current feature timestamp. It writes the exact six model inputs plus ratios, timestamp, schema version, and provenance to Redis with a one-hour TTL and publishes the update to `cogniflow.features.v1` with at-least-once delivery.

`GET /features/{session_id}` returns 404 for missing, 503 for stale/unavailable, and never fabricates values. `/predict` is unchanged. Runtime evidence: event `11111111-2222-4333-8444-555555555555` produced ratios `0.8/0.2` in Redis, Kafka, and the API. Rolling-window aggregates are not implemented; current values are latest-snapshot features.
