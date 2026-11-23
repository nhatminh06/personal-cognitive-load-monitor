# M2-S2A — Independent subsystem regression hardening

**Decision: PARTIAL.** Offline independent regressions pass; scoped MyPy remains unresolved. This is not a new container qualification or full Module II integration.

## A. Source baseline and changed files

Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. Pre-existing edits to `jobs/internal_job_runner.py` and `src/tests/test_internal_job_runner.py`, plus all untracked qualification reports, were preserved. Changed `Makefile` and `src/tests/test_airflow_cold_start.py`; added `src/tests/test_module2_independent_analytics.py` and this report. The M2-S1E fail closed Spark guard remains in force.

## B. Airflow regression coverage

Offline DAG import uses a fake Airflow SDK. Tests now assert all five edges in the six-task chain, two retries with ten-second delay, missing runner token rejection, and mocked transient and persistent HTTP failures. The fake SDK does not execute a task scheduler, so retry exhaustion, downstream scheduling, and run metadata remain covered by the prior isolated Airflow qualification only, not these offline tests. No external runner request is made.

## C. Trino/dbt regression coverage

Tests read the original retained three-row Parquet fixture and check its 18 fields, unique event IDs, two-session distribution, null user, 135 focus minutes, and average focus ratio. They assert six incremental Gold SQL models with merge configuration, one staging model, eight declared dbt tests, and quality summary SQL. These source and fixture checks do not rerun Trino, dbt MERGE, or persistence; their prior independent container evidence remains separate.

## D. Spark deferral regression coverage

The selected existing runner tests check failed Spark startup and direct submission before `subprocess.run`, an approved dbt command, unsupported kinds, and fail closed authentication. Existing Airflow cold start tests exercise the in-process lock release. No configured Spark image or process was invoked.

## E. MyPy diagnostic disposition

`.venv/bin/mypy jobs/internal_job_runner.py` reproduces six diagnostics in imported `jobs/bronze_to_silver.py`: untyped `boto3` and `botocore.config`; missing `delta.tables`, `pyspark`, and `pyspark.sql`; and an untyped `cogniflow_data.storage_accounting` import. No diagnostic points at the changed offline tests or runner guard. Installing the blocked Spark runtime or adding broad ignores is outside this milestone. Scoped MyPy is **FAIL**, pending safe typing resolution.

## F. Regression command and CI

`make module2-independent-regression` prints its offline scope and selects the Airflow cold start, internal runner, analytics fixture, Trino history, and historical feature tests. Pytest returns nonzero on failure. It requires no Docker daemon or live service. CI was unchanged.

## G. Actual verification results

| Command | Result |
| --- | --- |
| `make module2-independent-regression` | 27 passed |
| `.venv/bin/ruff check src/tests/test_airflow_cold_start.py src/tests/test_internal_job_runner.py src/tests/test_module2_independent_analytics.py jobs/internal_job_runner.py` | PASS |
| `.venv/bin/mypy jobs/internal_job_runner.py` | FAIL: six imported Spark typing diagnostics |
| `docker compose -f infra/module2/docker-compose.yml config --quiet` | PASS |
| `git diff --check` | PASS |

No Python application, Compose, Helm, or Terraform behavior changed. No broader regression suite was run.

## H. Preserved evidence and cleanup

The original fixture, qualification logs, raw scans, manifests, and Docker resources remain untouched. No test-owned container, image, network, or volume was created.

## I. Remaining limitations

The retained fixture is ignored local evidence and must remain available for this offline selection. The tests verify fixture and SQL contracts, not live aggregation, retry scheduling, MERGE execution, or restart persistence. Scoped MyPy remains unresolved. Spark is BLOCKED; full Module II is UNVERIFIED; cloud/Kubernetes are NOT QUALIFIED; production is NOT READY.

## J. Final decision and next milestone

**PARTIAL.** Next independent milestone: make the original three-row fixture a stable, reviewed test fixture with recorded hashes and expand offline dbt contract assertions, while keeping live analytics requalification and Spark security qualification separate.
