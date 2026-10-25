# Airflow orchestration

`cogniflow_bronze_to_gold` has six fail-fast tasks: source check, input validation, Spark transformation, Silver verification, dbt build/tests, and Gold-quality verification. Airflow 3.3.2 uses the public `airflow.sdk` API, LocalExecutor, and UID 50000. It has no Docker socket or Docker SDK. Spark and dbt run behind separate internal HTTP runners that accept authenticated requests for a fixed allowlist only, reject concurrent execution, enforce timeouts, and return bounded output. Their ports are not published to the host.

The production boundary is a Kubernetes-native executor: one service account per DAG, namespace-scoped RBAC, immutable job images, no host socket, no privileged pods, read-only root filesystems, resource quotas and workload identity for object storage. That design is cloud-deferred; it was not runtime-tested locally.

Runtime evidence: `airflow dags test cogniflow_bronze_to_gold` finished `success` after all six tasks in 163.24 seconds on 2026-10-25. An initial run exposed a 30-second orchestration timeout and Python 3.8 incompatibility in the Spark runner; both root causes were fixed before the successful clean run. The production boundary remains Kubernetes-native execution with namespace-scoped RBAC, immutable job images, workload identity, quotas, and no privileged pods; that cloud design was not runtime-tested here.
