# Airflow orchestration

`cogniflow_bronze_to_gold` has six fail-fast tasks: source check, input validation, Spark transformation, Silver verification, dbt build/tests, and Gold-quality verification. It uses the local Docker socket to execute already-running profile containers. This is appropriate only for an isolated developer machine; a production scheduler needs a restricted Kubernetes executor/service account.

Runtime evidence: the 2026-10-25 test run finished `success` after all six tasks. The earlier run failed on an XCom serialization defect and was fixed; retries did not mask the failure.
