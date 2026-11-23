# M2-S2C — Typed runner boundary closure

**Decision: PASS_TYPED_BOUNDARY (2026-11-21).** The original scoped MyPy command and independent offline regression both pass. Spark remains blocked.

## A. Baseline and initial diagnostics

Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. Existing source changes, untracked qualification reports, and ignored evidence were preserved. Read `AGENTS.md`, M2-S1E, M2-S2A, M2-S2B, and runner callers before editing. The original `.venv/bin/mypy jobs/internal_job_runner.py` reported:

```text
jobs/bronze_to_silver.py:10: error: Skipping analyzing "boto3": module is installed, but missing library stubs or py.typed marker  [import-untyped]
jobs/bronze_to_silver.py:11: error: Skipping analyzing "botocore.config": module is installed, but missing library stubs or py.typed marker  [import-untyped]
jobs/bronze_to_silver.py:12: error: Cannot find implementation or library stub for module named "delta.tables"  [import-not-found]
jobs/bronze_to_silver.py:13: error: Cannot find implementation or library stub for module named "pyspark"  [import-not-found]
jobs/bronze_to_silver.py:14: error: Cannot find implementation or library stub for module named "pyspark.sql"  [import-not-found]
jobs/bronze_to_silver.py:16: error: Skipping analyzing "cogniflow_data.storage_accounting": module is installed, but missing library stubs or py.typed marker  [import-untyped]
```

## B. Root cause and import graph

`jobs/internal_job_runner.py` imported `bronze_to_silver.load_bronze_accounted` inside its `/validate` HTTP branch. MyPy followed that import into `jobs/bronze_to_silver.py` and its unavailable Spark and untyped dependency imports. M2-S1E already rejected Spark startup and direct submission, but the HTTP branch could still call the Bronze validation function in a directly instantiated handler. The supported dbt `/run` path needs no Spark symbol.

## C. Architecture decision

The Spark-only validation branch is unreachable through a normally started runner under DEFER_SPARK. Remove that dependency and explicitly reject the endpoint after authentication, before request parsing, lock acquisition, Spark imports, or subprocess work. Preserve the shared dbt command, authentication, timeout, and locking flow. No typing setting or dependency changed.

## D. Minimal implementation

`jobs/internal_job_runner.py` returns HTTP 502 with `Spark runtime is security blocked` for authenticated Spark `/validate`; other authenticated `/validate` requests retain HTTP 404. Missing or incorrect credentials retain HTTP 401. The unused Spark import and validation call were removed. Spark startup and `run_job("spark", ...)` still raise before server binding or subprocess creation. The established DAG and production Spark job were unchanged.

## E. Deferral safety checks

Focused tests reject Spark startup before server binding and direct submission before subprocess invocation. HTTP tests reject Spark `/validate` for valid, invalid, and missing credentials; a Python import spy fails on any attempted `bronze_to_silver`, PySpark, or Delta import, and a subprocess spy fails on execution. The lock is left free. Existing dbt allowlist execution, invalid job kinds, token checks, and in-process lock tests continue to pass. No Spark process or Docker runtime was used.

## F. Original scoped MyPy

`.venv/bin/mypy jobs/internal_job_runner.py` → `Success: no issues found in 1 source file`. This is the unmodified original command. It establishes typing of the shared runner boundary; it does not establish typing or functionality of the separate Spark job.

## G. Independent regressions and static checks

| Check | Result |
| --- | --- |
| `make module2-independent-regression` | 29 passed in 0.11 seconds; prior 28 remain passing |
| `.venv/bin/mypy jobs/internal_job_runner.py` | PASS |
| `.venv/bin/ruff check src scripts jobs dags pipelines` | PASS |
| `docker compose -f infra/module2/docker-compose.yml config --quiet` | PASS, offline parsing only |
| `git diff --check` | PASS |

## H. Changed files

Modified `jobs/internal_job_runner.py`, `src/tests/test_internal_job_runner.py`, and `src/tests/test_airflow_cold_start.py`; added this report. All earlier modifications and qualification evidence were preserved.

## I. Remaining limitations

The Spark job itself remains untyped in this local development environment and is not exercised. Offline tests do not repeat the independent Airflow or Trino/dbt container qualifications. A user with direct shell/Docker control can bypass the runner guard; that is outside the supported authenticated interface.

## J. Final decision

**PASS_TYPED_BOUNDARY.** Airflow mock orchestration and independent Trino/dbt analytics retain their earlier bounded PASS statuses. Spark remains BLOCKED with DEFER_SPARK_ENFORCED; end-to-end Module II remains UNVERIFIED; cloud/Kubernetes are NOT QUALIFIED; production is NOT READY.
