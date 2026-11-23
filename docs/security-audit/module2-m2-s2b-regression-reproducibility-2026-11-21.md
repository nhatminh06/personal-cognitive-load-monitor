# M2-S2B — Independent regression reproducibility and typing closure

**Decision: PARTIAL.** The offline regression is portable; the original scoped MyPy command still fails with six Spark import diagnostics.

## A. Source baseline

Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. Existing modifications to `Makefile`, the runner and runner tests, and Airflow tests, plus all untracked qualification reports and raw evidence, were preserved. Read `AGENTS.md`, M2-S2A, M2-S1E, the regression target, original fixture generator, and selected tests.

## B. Fixture provenance and checksums

The M2-S2A offline suite depended on only one ignored evidence file: `build/module2-analytics-qualification/fixture/session_features/part-00000.parquet`. It is a 5,808-byte synthetic table with three invented event IDs, two invented session IDs, one null user, synthetic Kafka provenance, and no credentials or personal data. The source generator uses fixed dates and values.

Copied the exact bytes to tracked `tests/fixtures/module2_session_features.parquet`; `cmp` succeeded and both SHA-256 values are `85aa6318227dcf7ce01d3cb0218114bc761d66779957795fbf5b86893d074961`. The original ignored Parquet and Delta log were not changed. The test now verifies this checksum before reading the 18-field, three-row oracle: 135 focus minutes; session-a has two rows and 75 minutes, session-b one row; one null user; average focus ratio `0.8333333333333334`. Missing fixture yields an explicit assertion.

## C. Portable regression verification

Created a temporary source tree from `git archive HEAD`, overlaid the intended local source changes and tracked fixture, and excluded `build/module2-analytics-qualification`. Using the existing Python 3.11 virtual environment with `PYTHONPATH` set to that copy, the exact five-file pytest selection passed **28 tests** (the prior 27 plus the missing-fixture test) in 0.13 seconds. The first copy run passed the prior 27; after overlaying the new test, all 28 passed. The copy used no Docker daemon, Spark executable, cloud endpoint, or credentials. It is an isolated source copy, not a newly installed dependency environment.

## D. Six MyPy diagnostic dispositions

The original command `.venv/bin/mypy jobs/internal_job_runner.py` follows the runner's `/validate` branch import of `bronze_to_silver`, then analyzes that job. The unchanged six diagnostics are:

```text
jobs/bronze_to_silver.py:10: error: Skipping analyzing "boto3": module is installed, but missing library stubs or py.typed marker  [import-untyped]
jobs/bronze_to_silver.py:11: error: Skipping analyzing "botocore.config": module is installed, but missing library stubs or py.typed marker  [import-untyped]
jobs/bronze_to_silver.py:12: error: Cannot find implementation or library stub for module named "delta.tables"  [import-not-found]
jobs/bronze_to_silver.py:13: error: Cannot find implementation or library stub for module named "pyspark"  [import-not-found]
jobs/bronze_to_silver.py:14: error: Cannot find implementation or library stub for module named "pyspark.sql"  [import-not-found]
jobs/bronze_to_silver.py:16: error: Skipping analyzing "cogniflow_data.storage_accounting": module is installed, but missing library stubs or py.typed marker  [import-untyped]
```

The boto3/botocore errors are absent third-party typing metadata; Delta/PySpark are absent Spark development packages; the storage accounting module is repository code reached through the job import but is not presented as typed to this MyPy import context. `--follow-imports=skip` makes the runner check pass, confirming the chain, but changes the check scope and is **not** counted as a pass for the original command. No genuine runner type error was found. Resolving all six soundly requires a dedicated typed Spark development context and package boundary review; no Spark package was installed, no dummy stubs or broad suppression were added, and runtime imports remain unchanged.

## E. Tests and static checks

| Command | Actual result |
| --- | --- |
| `make module2-independent-regression` | 28 passed, 0.12 seconds |
| Source-only copy pytest selection with original virtual environment | 28 passed, 0.13 seconds |
| `.venv/bin/ruff check src scripts jobs dags pipelines` | PASS |
| `.venv/bin/mypy jobs/internal_job_runner.py` | FAIL, six diagnostics above |
| `docker compose -f infra/module2/docker-compose.yml config --quiet` | PASS; configuration parsing only |
| `git diff --check` | PASS |

## F. Changed files

Added `tests/fixtures/module2_session_features.parquet`, updated `src/tests/test_module2_independent_analytics.py` to use and verify it, and added this report. The original ignored evidence and qualified runtime behavior were not changed.

## G. Preserved qualification boundaries

Airflow remains PASS for local mock orchestration; Trino/dbt remains PASS for its earlier independent local analytics run. This milestone proves offline contracts and portability only. Spark remains BLOCKED with DEFER_SPARK_ENFORCED; full Module II remains UNVERIFIED; cloud/Kubernetes remain NOT QUALIFIED; production is NOT READY.

## H. Remaining limitations

The original scoped MyPy check fails. The source-only copy uses the existing virtual environment, so it does not establish a clean dependency installation. Offline SQL assertions do not execute dbt MERGE or prove database persistence. Spark security clearance and functional integration require separate milestones.

## I. Final decision

**PARTIAL.** Fixture portability is closed; typing closure remains open without a safe, policy preserving fix in this milestone.
