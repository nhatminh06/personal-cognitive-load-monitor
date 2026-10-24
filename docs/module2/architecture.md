# Module II architecture

Module II extends Module I; it does not put Kafka or the lakehouse on the synchronous `/predict` path.

```mermaid
flowchart TB
  CLIENT[Demo or generator] --> EVENTS[POST /events]
  EVENTS --> KAFKA[Kafka session-events.v1]
  KAFKA --> BRONZE[Bronze writer]
  BRONZE --> MINIO[MinIO immutable JSONL]
  MINIO --> SPARK[Spark 3.5 batch]
  FEATURES[shared feature contract] -. parity vectors .-> SPARK
  SPARK --> DELTA[Delta Silver]
  DELTA --> TRINO[Trino]
  TRINO --> DBT[dbt Gold models]
  AIRFLOW[Airflow DAG] --> SPARK
  AIRFLOW --> DBT
  KAFKA --> FLINK[Flink watermarks + dedup]
  FLINK --> ROLLING[Sliding windows]
  FLINK --> TUMBLING[Tumbling windows]
  ROLLING --> REDIS
  ROLLING --> FEATURETOPIC
  TUMBLING --> FEATURETOPIC
  FLINK --> LATE[Late-event quarantine]
  REDIS[Redis freshness-safe online features]
  FEATURETOPIC[Kafka features.v1]
  REDIS --> FEATUREAPI[GET /features/{session_id}]
  PREDICT[POST /predict] --> MODEL[Module I inference modes]
```

## Boundaries

- `POST /predict` and its request/response models remain unchanged and independent.
- `POST /events` publishes a versioned envelope only after Kafka acknowledges it.
- Bronze acknowledges Kafka offsets only after durable object storage succeeds. Delivery is at least once; deterministic object keys make replay duplicate-safe.
- Spark is the sole Silver writer. Trino/dbt read Silver and create Gold on a schedule, avoiding concurrent Delta writers.
- Flink is the genuine streaming engine. Redis is a timestamped online projection, not a source of truth.
- Shared JSON parity vectors carry exact ordered names, units, schema version, timestamps and zero-total cases. Python and Java tests consume the same file; the Spark runtime uses the same checked expressions.

## Module I extension points

Graphify baseline: 281 nodes, 419 edges, 24 communities. `main.py` is the API composition point; `schemas.py` is the validation boundary; `feature_vector` is the train/serve parity anchor. Module II code belongs in a separate `cogniflow_data` package and thin API router so batch dependencies never enter the core API process.

The prior post-implementation graph contained 497 nodes, 838 edges and 35 communities. The final code-only structural update contains 542 nodes, 944 edges and 31 communities. It confirms the native Spark/Flink feature implementations remain separated from Module I by the shared fixture/API contract; no reverse import from `preprocessing_api` into Kafka/storage was introduced. Spark and Flink necessarily express the ratio formula in their native runtimes, so the shared fixture is the cross-language contract rather than a runtime import.

No circular dependency is permitted: Module II may import the stable feature contract, while `preprocessing_api.features` must not import Kafka, storage, or streaming modules.
