# Module II grading matrix

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Versioned Kafka ingestion | Runtime verified | 202 accepted only after broker acknowledgment |
| MinIO Bronze provenance | Runtime verified | Exact event readback and durable-offset ordering |
| Spark + true Delta Silver | Runtime verified | Delta log, reopen, one-row idempotent merge |
| Trino Delta query | Runtime verified | Actual Silver ratios queried |
| dbt Gold and tests | Runtime verified | Two 15/15 consecutive builds |
| Airflow orchestration | Runtime verified | Six-task DAG state success |
| Flink → Redis/Kafka | Runtime verified | Genuine DataStream job and timestamped feature |
| Online feature adapter | Unit + runtime verified | Explicit missing/stale/unavailable responses |
| Regression / coverage | Verified | 59 passed; 87.79% combined Python coverage; Ruff/MyPy green |
| DVC / notebooks / Docker | Verified | Cached reproducibility; four notebooks; both inference modes |
| Synthetic generator | Partial | Deterministic, seeded, bounded JSONL profiles; Kafka publishing, fault injection, resume and benchmark manifests remain pending |
| Graphify | Structural only | 497 nodes/838 edges/35 communities; semantic, SQL and HCL extraction unavailable |
| Rolling stream windows | Not implemented | Latest snapshot only |
| Module II Grafana dashboard | Not verified | API metrics exist; dashboard/runtime integration pending |
| 100GB processing | Deferred | Generator is bounded; no large run performed |
| Cloud/HA controls | Cloud deferred | No paid resources or remote deployment |
| UI/UX Module II panel | Not implemented | UI/UX Pro Max unavailable; Module I UI preserved |
