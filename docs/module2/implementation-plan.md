# Module II implementation plan

Work proceeds in dependency order and records runtime evidence after each gate.

1. **A — baseline:** preserve Module I tests/contracts; pin a compatible, resource-bounded stack.
2. **B — ingestion:** Pydantic v1 event envelope, JSON Schema, Kafka KRaft, `/events`, producer/consumer, deduplication and dead-letter routing.
3. **C — Bronze:** MinIO initialization and a durable micro-batch writer with deterministic keys and offset-after-storage semantics.
4. **D — Silver:** Spark/Delta transformation, validation quarantine, merge-based idempotency, history and parity tests.
5. **E — analytics:** Trino Delta catalog plus dbt staging/Gold models and reconciliation tests.
6. **F — orchestration:** a lightweight Airflow LocalExecutor/SQLite deployment running the real Spark and dbt commands sequentially.
7. **G — streaming:** Flink Kafka source, event-time watermarks/windows, Redis freshness-safe sink and versioned feature topic.
8. **H — integration:** sequential batch and streaming demonstrations, failure recovery, observability, UI, documentation and regression.

Every runtime group is an opt-in Compose profile. Kafka+MinIO is tested first; it is stopped before Spark/Trino or Flink. Full-stack claims require real evidence and are otherwise marked unavailable.

## API compatibility guardrails

The four measurements, optional `feature_as_of`, response schema, ordered six features, levels, `synthetic_proxy` provenance and fail-closed production inference behavior are frozen. `/events`, `/features`, and pipeline-status endpoints are additive.

## Verification strategy

- Unit tests use dependency injection and local temporary storage.
- Integration tests are explicitly marked and require the corresponding profile.
- Actual broker, object store, Delta, SQL, DAG, Flink and Redis evidence is recorded separately from mocks and static configuration.
- No test generates large data by default; tiny deterministic fixtures are the default.
