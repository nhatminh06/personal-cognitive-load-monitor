# Airflow orchestration

`cogniflow_bronze_to_gold` has six fail-fast tasks: source check, input validation, Spark transformation, Silver verification, dbt build/tests, and Gold-quality verification. The reproducible local DAG still uses Docker exec, but it is isolated under the explicitly named `orchestration-dev` profile and mounts the socket read-only. Read-only does **not** make the Docker API safe: access to `exec` remains effectively host-root authority. The profile is absent from Helm/cloud configuration and must never be exposed on a shared runner.

The production boundary is a Kubernetes-native executor: one service account per DAG, namespace-scoped RBAC, immutable job images, no host socket, no privileged pods, read-only root filesystems, resource quotas and workload identity for object storage. That design is cloud-deferred; it was not runtime-tested locally.

Runtime evidence: the 2026-10-25 test run finished `success` after all six tasks. The earlier run failed on an XCom serialization defect and was fixed; retries did not mask the failure.
