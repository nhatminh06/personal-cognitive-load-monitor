# Module II grading matrix

Statuses mean exactly: **implemented** (source exists), **statically validated**
(render/lint only), **locally runtime verified**, **cloud runtime verified**, or
**not completed**. Configuration alone never advances a runtime status.

| Rubric criterion | Weight | Implementation | Exact evidence and tests | Missing requirement / acceptance condition |
|---|---:|---|---|---|
| MinIO object storage | 10% | Historical MinIO code; active SeaweedFS S3 in `infra/module2` | SeaweedFS bucket/write/checksum/read/restart/Spark evidence in `testing.md` | **Not completed as MinIO**: instructor equivalence or licensed maintained MinIO runtime required |
| Trino serving/transformation | 10% | Trino 478 + dbt Gold | Locally runtime verified Silver queries and two 15/15 dbt builds | Re-run demonstration at final commit |
| Delta Lake | 10% | Delta 3.3.2 Silver table | Locally runtime verified log/history/reopen/idempotent MERGE | Re-run demonstration at final commit |
| Spark batch | 10% | Spark 3.5.5 Bronze→Silver | Locally runtime verified fixture and reconciliation | SEC-022 keeps this image isolated/local only |
| Kafka broker | 10% | Kafka 3.9.2, versioned topic | Locally runtime verified broker acknowledgments and durable offsets | Re-run demonstration at final commit |
| Flink streaming/windows | 10% | Flink 1.20.5 event-time sliding + tumbling windows | Locally runtime verified watermarks, lateness, dedup, checkpoint restoration, Redis freshness; JUnit fixtures | Re-run demonstration at final commit |
| Airflow orchestration | 10% | Airflow 3.3.2 six-task DAG | Locally runtime verified 163.24-second successful DAG | Re-run demonstration at final commit |
| Four cloud deployments | 20% | GKE readiness patterns only | Statically validated where shared infrastructure applies | **Not completed**: four separately accepted runtime deployments required |
| Dataset strictly >100 GB | 10% | Partitioned resumable generator + benchmark plan | Small fixtures validate exact bytes, resume integrity and safety gates | **Not completed** until >100,000,000,000 bytes are processed and reconciled |

Current maximum supported score from existing runtime evidence is therefore
60/100 before instructor judgment on SeaweedFS equivalence; no cloud or 100 GB
points are claimed.

| Requirement | Status | Evidence / limitation |
|---|---|---|
| Versioned Kafka ingestion | Runtime verified | 202 accepted only after broker acknowledgment |
| SeaweedFS Bronze provenance | Runtime verified | Exact event readback and durable-offset ordering; not claimed as MinIO credit |
| Spark + true Delta Silver | Runtime verified | Delta log, reopen, one-row idempotent merge |
| Trino Delta query | Runtime verified | Actual Silver ratios queried |
| dbt Gold and tests | Runtime verified | Two 15/15 consecutive builds |
| Airflow orchestration | Runtime verified | Six-task DAG state success |
| Flink → Redis/Kafka | Runtime verified | Genuine DataStream job and timestamped feature |
| Online feature adapter | Unit + runtime verified | Explicit missing/stale/unavailable responses |
| Regression / coverage | Verified | 59 passed; 87.79% combined Python coverage; Ruff/MyPy green |
| DVC / notebooks / Docker | Verified | Cached reproducibility; four notebooks; both inference modes |
| Synthetic generator | Verified locally | Deterministic Kafka/file output, duplicate/invalid/late injection, authoritative-manifest reconciliation, byte/free-space guards; 100GB execution deferred |
| Graphify | Structural only | 497 nodes/838 edges/35 communities; semantic, SQL and HCL extraction unavailable |
| Rolling/tumbling stream windows | Runtime verified | Deterministic event-time window, late policy, dedup, checkpoint restore and Redis stale-write evidence |
| Cross-language feature parity | Runtime verified | Shared JSON contract consumed by Python/JUnit; real Spark 3.5.5 fixture run passed all six ordered fields |
| Module II Grafana dashboard | Runtime verified, partial scope | API/JM/TM targets up and dashboard provisioned; batch/Airflow exporters remain pending rather than fabricated |
| Airflow execution security | Locally isolated | Insecure socket path renamed `orchestration-dev`; Kubernetes-native boundary documented and cloud-deferred |
| 100GB processing | Deferred | Generator is bounded; no large run performed |
| Cloud/HA controls | Cloud deferred | No paid resources or remote deployment |
| UI/UX Module II panel | Not implemented | UI/UX Pro Max unavailable; Module I UI preserved |
