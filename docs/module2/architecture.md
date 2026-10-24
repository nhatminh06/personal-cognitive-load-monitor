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
  KAFKA --> FLINK[Flink event-time job]
  FLINK --> REDIS[Redis online features]
  FLINK --> FEATURETOPIC[Kafka features.v1]
  REDIS --> FEATUREAPI[GET /features/{session_id}]
  PREDICT[POST /predict] --> MODEL[Module I inference modes]
```

## Boundaries

- `POST /predict` and its request/response models remain unchanged and independent.
- `POST /events` publishes a versioned envelope only after Kafka acknowledges it.
- Bronze acknowledges Kafka offsets only after durable object storage succeeds. Delivery is at least once; deterministic object keys make replay duplicate-safe.
- Spark is the sole Silver writer. Trino/dbt read Silver and create Gold on a schedule, avoiding concurrent Delta writers.
- Flink is the genuine streaming engine. Redis is a timestamped online projection, not a source of truth.
- Shared JSON parity vectors prove Spark/Python feature parity. The Flink formulas use the same zero-total rule, but Java-level fixture automation remains pending.

## Module I extension points

Graphify baseline: 281 nodes, 419 edges, 24 communities. `main.py` is the API composition point; `schemas.py` is the validation boundary; `feature_vector` is the train/serve parity anchor. Module II code belongs in a separate `cogniflow_data` package and thin API router so batch dependencies never enter the core API process.

Post-implementation structural update: 497 nodes, 838 edges, 35 communities. The new API router/online adapter form one bounded community, Kafka primitives another, and Bronze storage another. The graph confirmed that `main.py` remains the only composition edge from Module I to `cogniflow_data`. Spark and Flink duplicate ratio expressions because their runtimes cannot import the Python helper; Spark parity is fixture-tested, while Java parity automation remains a documented gap. SQL/HCL and semantic extraction were unavailable, so their relationships are represented by this reviewed diagram rather than claimed Graphify output.

No circular dependency is permitted: Module II may import the stable feature contract, while `preprocessing_api.features` must not import Kafka, storage, or streaming modules.
