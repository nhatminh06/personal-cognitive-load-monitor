# Module II independent Airflow qualification — 2026-11-21

## Decision and scope

**PASS** for local Apache Airflow orchestration against test-owned mocked dependencies only.

This qualification does not qualify Spark execution, real Spark integration, end-to-end Module II, Kubernetes or GCP, cloud readiness, or production deployment. Spark was neither started nor invoked. SEC-022 was not changed.

| Area | Result | Evidence |
| --- | --- | --- |
| Preflight and isolation | PASS | 8,507,801,600 bytes available immediately before startup; 15 GiB RAM, 15 GiB swap, 147 GiB disk free; dedicated Compose project, internal network, and volumes |
| Airflow image security | PASS | Airflow 3.4.0; uid/gid 50000; exact image and fresh Trivy scan below |
| DAG import and validation | PASS | No import errors; exact six-task chain, retry configuration, and `max_active_runs=1` confirmed |
| Six-task execution | PASS | All six tasks succeeded against mocks in 14.229198 seconds |
| Authentication and retries | PASS | Missing token failed before request; invalid token returned 401; transient 500 retried once and succeeded; three persistent 500 responses exhausted configured retries and failed the run |
| Persistence | PASS | Successful and failed run/task metadata remained after restarting the Airflow container with its volume preserved |
| Resource safety | PASS | Peak Airflow 223.7 MiB / 640 MiB and 1.17% CPU; metadata volume 1.012 MB; no OOM events or unexpected restarts |
| Regression results | PASS | 701 passed, 2 skipped; focused 25 passed; Ruff, scoped MyPy, Compose validation, and `git diff --check` passed |
| Evidence retention | PASS | Raw ignored reports and logs under `build/`; SHA-256 manifest retained |
| Remaining blockers | BLOCKED | Real Spark remains security-blocked; full integration, cloud, and production qualification were deliberately not attempted |

## Preflight and isolation

- Git branch `main` was at `e9cefee`, two commits ahead of `origin/main`. The pre-existing untracked Trino/dbt qualification document was preserved.
- Existing Kafka, Flink, Redis, SeaweedFS, Trino, Module I, and retained qualification resources were inventoried and not modified. The test used Compose project `cogniflow-airflow-qualification-20261121` only.
- Immediately before startup, host available memory was 8,507,801,600 bytes, above the required 6 GiB threshold. Initial disk state was 473 GiB total, 147 GiB free (69% used). Post-test available memory was 8.3 GiB with 13 GiB swap free.
- The isolated network was internal-only. Its only service aliases were `spark`, `dbt-runner`, and `trino`, all bound to the qualification mock. No real Spark, dbt runner, or Trino container was joined or contacted.

## Image security gate

- Tag: `cogniflow-airflow:c45-patched`
- Image ID: `sha256:57126c3aa4cd0c62eafe4b65fc73d708346f8c06f2e0468ddc83fbc8c635178d`
- Runtime: Apache Airflow `3.4.0`, user `airflow`, uid/gid `50000:50000`; packaging tools were absent.
- Fresh Trivy 0.76.2 OS and Python dependency scan: **0 HIGH, 0 CRITICAL**. The image was not executed until this gate passed.
- Scan databases were updated on 2026-11-21 at 01:10:48 UTC (vulnerability DB) and 00:58:42 UTC (Java DB).
- Raw scan: `build/security-scans/airflow-independent-2026-11-21/airflow.json`, SHA-256 `498250b521b65b8d06134e03c9d90b779766330582134d44fbf13c86342c214b`.

## DAG validation and execution

Airflow reported no import errors. Direct DAG inspection confirmed this unchanged chain:

`check_source -> validate_input -> spark_bronze_to_silver -> verify_silver -> dbt_build -> verify_gold_quality`

Every task retained `retries=2` and a 10-second retry delay. The DAG retained `max_active_runs=1`.

The successful run at logical date `2026-11-21T13:00:00Z` completed as follows:

| Task | Final state | Attempts |
| --- | --- | --- |
| `check_source` | success | 1 |
| `validate_input` | success | 1 |
| `spark_bronze_to_silver` | success | 2 (first mocked request returned 500) |
| `verify_silver` | success | 1 |
| `dbt_build` | success | 1 |
| `verify_gold_quality` | success | 1 |

The event log shows only the expected mock health, validation, fixed runner, and Trino SQL endpoints. No external endpoint was reachable from the internal-only network. Mocked Spark success is orchestration evidence only, not Spark integration evidence.

An initial run at logical date `12:00Z` failed because the test mock attempted to write to a root-owned test path. That harness-only defect was corrected without changing the production DAG or runner and the run was discarded from qualification results; its failed metadata remains visible for auditability.

## Authentication and failure behavior

- Calling the real DAG helper without `JOB_RUNNER_TOKEN` raised `RuntimeError: JOB_RUNNER_TOKEN is not configured` before any request.
- A request with an invalid Bearer token received HTTP 401 and did not trigger a job.
- The successful scenario returned HTTP 500 for the first mocked Spark runner call. Airflow recorded `up_for_retry` at attempt 1, waited the configured 10 seconds, and succeeded at attempt 2.
- The persistent scenario returned HTTP 500 three times. Airflow recorded two `up_for_retry` states followed by `failed` on attempt 3; downstream tasks were `upstream_failed`, and neither dbt nor gold verification was contacted. The DAG run failed in 26.220942 seconds.

## Persistence and resources

The test-owned Airflow container was restarted while preserving `cogniflow-airflow-qualification-20261121_airflow-home`. `airflow db check` passed afterward. The successful run, its six final task states, the transient retry record, and the persistent-failure run were all still queryable.

- Peak sampled Airflow usage: 223.7 MiB / 640 MiB, 1.17% CPU.
- Mock usage: approximately 12 MiB / 64 MiB.
- Metadata volume: 1.012 MB.
- Airflow and persistent mock: `OOMKilled=false`, no unexpected restart. The transient mock's exit 137 followed an intentional `docker compose stop`; it was not an OOM and had `RestartCount=0`.
- Post-test host: 8.3 GiB memory available, 13 GiB swap free, 147 GiB disk free.

## Regression and static validation

- `make test`: **701 passed, 2 skipped**, 87.00% coverage (five warnings).
- Focused Airflow, authenticated-runner, Module II rehearsal, and Spark-isolation tests: **25 passed**.
- A scoped MyPy run exposed an existing invariant-`dict` annotation at the runner JSON reply boundary. The signature was narrowed to accept `Mapping[str, object]`; this is type-only and does not change runtime behavior. Post-fix focused tests: **9 passed**.
- `.venv/bin/ruff check src scripts jobs dags pipelines`: passed.
- Scoped MyPy for the DAG and authenticated runner with missing third-party imports ignored: passed.
- `docker compose -f infra/module2/docker-compose.yml --profile orchestration-dev config --quiet`: passed.
- Qualification Compose resolution and validation: passed.
- `git diff --check`: passed.
- Helm lint and Terraform validation were not applicable because no Helm, Kubernetes, GKE, or Terraform source was changed or exercised.

## Evidence retention

Raw evidence is intentionally ignored and retained locally under:

- `build/airflow-qualification/`
- `build/security-scans/airflow-independent-2026-11-21/`

Key checksums:

| Evidence | SHA-256 |
| --- | --- |
| Trivy JSON | `498250b521b65b8d06134e03c9d90b779766330582134d44fbf13c86342c214b` |
| Successful Airflow metadata | `6ba1f21968281e371fda0015315a798b6025172a35a71444bd520f517121ada5` |
| Transient endpoint events | `19f2519c32755289c87c02b0aec634095487681ea4215aa83dfcbf369dfddc80` |
| Authentication events | `1a6c3068a511e559f436a43f54462132f14a306af16ad9cedc92369a0d7801a3` |
| Persistent failure metadata | `c65e813d1b917490eadcfda98e4a5743d96644f4729e19c625997c00282f9f70` |
| Persistent endpoint events | `b186634cd42a23d1dd110be7d6cfc5ad2db7391fd5ab34dc0e58fcc0d3a988d1` |
| Post-restart metadata | `16000ab2f778d9b16ec3e10d306a9f6f578410286ad20c6546631c47860952f0` |
| Container inspection | `652658dd83e2634f4182cea23e0859a2d145d7f438a1881feeced50deb750bbb` |
| Runtime log | `5943fca4654a20083b831bbc7b1061c7c9e9a9561d354fe6273eb6036203c03e` |

The complete local manifest is `build/airflow-qualification/SHA256SUMS`.

## Final qualification decision

**PASS** — the exact patched Airflow 3.4.0 image is independently qualified for local execution of the existing six-task CogniFlow DAG against authenticated, test-owned mocks. The evidence demonstrates import correctness, ordering, fail-closed credentials, bounded retries, persistent failure propagation, metadata persistence, and operation within the imposed resource limits.

Real Spark execution remains **BLOCKED**. Full Module II integration, cloud readiness, and production deployment remain **UNVERIFIED** and are not implied by this result.
