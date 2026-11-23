# Module II independent Trino + dbt local qualification — 2026-11-21

## Decision

**Independent synthetic Silver → SeaweedFS S3 → Trino → dbt Gold path: PASS.**

This result is bounded to the exact local images and three-row fixture recorded
below. It does not qualify Bronze → Spark → Silver, the full Module II
rehearsal, GKE, cloud deployment, production readiness, scalability, or model
approval. Spark was not started and remains security blocked. SEC-022 and the
full-rehearsal image allowlist were not changed.

## A. Environment and preflight — PASS

- Host: CachyOS Linux x86_64, branch `main`, HEAD `e9cefee`, two unpublished
  commits ahead of `origin/main`; the tracked working tree was clean at start.
- Recent commits: `e9cefee`, `835fca9`, `64e2bb6`, `e5248ae`, `18a34fb`.
- Initial memory: 15 GiB physical, 8.6 GiB available; 15 GiB zram swap, 13 GiB
  free. The 6 GiB start gate passed. Memory PSI was zero over 10/60/300 seconds.
- Disk: 473 GiB total, 152 GiB available (68% used).
- The existing `cogniflow-module2` Kafka, Flink, Redis, SeaweedFS, networks, and
  volumes were inventoried and left running. The stopped
  `cogniflow-module1-qualification` control plane was not changed.
- Qualification project: `cogniflow-analytics-qualification-20261121`, with
  dedicated networks and volume, private local credentials, and loopback-only
  S3/Trino ports 19000/18081. The resolved Compose configuration passed before
  startup. Only SeaweedFS, S3 gateway, initializer, Trino, and transient dbt
  containers were used.

## B. Images and security — PASS

Trivy 0.76.2 scanned OS and language packages using vulnerability DB 2 updated
2026-11-21 01:10:48 UTC and Java DB 1 updated 2026-11-21 00:58:42 UTC. Counts
are scanner occurrences; no finding was suppressed.

| Image | Exact local image ID | HIGH | CRITICAL | Raw JSON SHA-256 |
|---|---|---:|---:|---|
| `cogniflow-trino:c44-patched` | `sha256:6d52676251294a650245065c1b99e9af53299608b5e200d80ad10fe6a7a125a1` | 0 | 0 | `105f1bcb7f6c8933608e6102cb42af3f98a5d146014ebfe4d40598630b1750a8` |
| `cogniflow-dbt-trino:c42-alpine` | `sha256:b6694cc0936e388906a20073a15224e29ea47f28c44526181c0d5e21d1adf019` | 0 | 0 | `3c08c2b398923dc1b703bc34630713057b7a88b9800e63eaee5518585972ab98` |
| `cogniflow-seaweedfs:c42-go-patched` | `sha256:52b36207518a817ea8b57c08fbbf3b6fd2353934a48d40cefc9810bd541008b6` | 0 | 0 | `d678ac444ad041e380fc6aa6ce07aff0b5669e3e698f079127b73b591d07677f` |
| `cogniflow-minio-init:c42-alpine-upgrade` | `sha256:7054ff6d153b37d23d62501c408d8c360cf9223fb3809a1533f8c492f3955b0e` | 0 | 0 | `b4bcc83d746df79abccbdeed6720d3c0508d78857ec37ede5b4c2d182ce905fb` |

The two repository-defined images built successfully. Trino CLI reported 484;
dbt reported core 1.11.14 and adapter 1.10.6. The dbt build-time `pip check`
reported no broken requirements. These rebuilt IDs intentionally do not replace
historical IDs or the rehearsal allowlist.

Raw reports are retained outside tracked source under
`build/security-scans/module2-analytics-2026-11-21/`.

## C. S3 and Trino connectivity — PASS

Both isolated buckets were created, SeaweedFS and its S3 gateway became
healthy, and the initializer exited zero. Trino became healthy and `SELECT 1`
returned 1. The catalog requires the canonical isolated bucket name
`cogniflow-lakehouse` because `hive.metastore.catalog.dir` is fixed in the
repository configuration; an initial custom bucket name failed closed before
schema creation and was corrected without sharing storage.

## D. Synthetic Delta Silver fixture — PASS

The deterministic fixture contains three records across `session-a` and
`session-b`. It implements all current Silver/dbt fields: event/session/user
identity, UTC event and ingestion timestamps, schema/source, four input
features, Kafka provenance, both ratios, `event_date`, and `processed_at`.
`event-a2.user_id` is null to exercise nullable handling.

- Parquet SHA-256: `85aa6318227dcf7ce01d3cb0218114bc761d66779957795fbf5b86893d074961`
- Delta log SHA-256: `d28efa1a8b0e586f2ec3363ec0a438924a4f4294db7241de53aa91513da37dc0`
- Upload/readback checksums matched byte-for-byte.
- Local Parquet validation found 3 rows and 18 fields; the transaction log had
  the expected commit, protocol, metadata, and add actions.

Independent oracle and observed Trino results matched:

| Result | Expected | Observed |
|---|---:|---:|
| rows | 3 | 3 |
| focus minutes | 135 | 135 |
| average focus ratio | 0.8333333333333334 | 0.8333333333333334 |
| sessions | 2 | 2 |
| null users | 1 | 1 |
| `session-a` events / focus / average ratio | 2 / 75 / 0.75 | 2 / 75 / 0.75 |
| `session-b` events / focus / average ratio | 1 / 60 / 1.0 | 1 / 60 / 1.0 |

## E. dbt Gold models and tests — PASS

`dbt parse` passed. Current discovery found 7 models (one staging view and six
incremental Gold models), 8 data tests, one source, and 499 macros. `dbt debug`
validated the profile, project, adapter, and live connection, but returned
nonzero solely because the hardened image intentionally has no Git executable;
Git was not installed.

The first `dbt build` passed all 15 discovered nodes: 7 model successes and 8
test passes, with 0 warnings, errors, or skips. Gold matched the oracle:

- daily: 1 row, 3 events, 135 focus minutes, ratio 0.8333333333333334;
- sessions: 2 rows and 3 events; `session-a` 2/0.75/0.25 and `session-b`
  1/1.0/0.0;
- data quality: 3 accepted, 0 stale;
- deadline pressure: 3 rows; distraction trend: 1 row; workload: 2 rows.

First-run `run_results.json` SHA-256:
`19570ee0a542588b45143695fce40f2391fa6b5069e08f09c45ab7b2df9b54ff`.

## F. Incremental execution and persistence — PASS

The second build passed the same 15 nodes with 0 warnings, errors, or skips and
used `MERGE` for all six incremental models. Counts and aggregates were
unchanged: one daily row, two session rows, and three reconciled events.
Second-run `run_results.json` SHA-256:
`849e477733fe3d2404f9e680f7a33e50acfcb387d532c0c26d1d2241009d6f5c`.

Only the test-owned Trino container was restarted. After it returned healthy,
Silver remained 3 rows / 135 focus minutes / 2 sessions and Gold remained two
session rows / three events plus one daily row / 135 focus minutes.

## G. Resources — PASS with one unverified metric

- Sampled service maxima: Trino 883.2 MiB and 12.60% CPU; SeaweedFS 102.6 MiB
  and 0.31% CPU; S3 gateway 41.75 MiB and 0.14% CPU.
- The transient dbt peak was not sampled and is **UNVERIFIED**; historical
  measurements were not promoted to this run.
- Host available memory was 8.6 GiB initially, 8.9 GiB immediately before
  startup, and 8.3 GiB after execution. Swap remained available.
- The isolated volume used 207.6 KiB. No tested service was OOM-killed, no
  health check failed after readiness, and no unexpected restart occurred.
- This small fixture provides no scalability or production-performance claim.

## H. Regression results — PASS

- Focused Trino/history/evidence/rehearsal tests: 28 passed.
- Full `make test`: 701 passed, 2 skipped, 87.00% coverage (81% required).
- Ruff over `src scripts jobs dags pipelines`: passed.
- Strict scoped MyPy was blocked only by absent third-party stubs for
  `requests`, `boto3`, and `botocore`; the same two-file scope passed with
  `--ignore-missing-imports` and no repository-owned errors.
- Lake + analytics Compose validation: passed.
- `git diff --check`: passed.
- Helm and Terraform were not rerun because no Helm, Kubernetes, Terraform, or
  cloud source changed and no such environment was exercised.

## I. Changed files and retained evidence

The only tracked change is this qualification record. Ignored local evidence
under `build/module2-analytics-qualification/` retains the resolved Compose
configuration, private-mode environment file, fixture generator and objects,
dbt logs/artifacts, runtime logs, and container inspection. Runtime log SHA-256:
`3249972edd971e96ed41835793dcdc8c80a605b88af54aa1640709cbba44838b`;
container inspection SHA-256:
`09e42bc62499ca81eba3586b848541a2856f8877fbe5f6e0c244e64d24dca83f`.

## J. Remaining blockers

- Spark and Bronze → Spark → Silver integration remain blocked/unqualified.
- The full Module II rehearsal remains unqualified.
- Cloud, GKE, production, scalability, and model approval remain unqualified.
- Rebuilt image IDs require a new scan on every rebuild and are not approved
  for publication or substitution into the rehearsal allowlist.
- dbt peak memory remains unverified for this run; strict MyPy requires the
  repository's missing external stub packages if it is to become a hard gate.

## K. Final qualification matrix

| Scope | Status |
|---|---|
| Preflight and isolation | PASS |
| Exact-image security gate | PASS |
| S3 and Trino connectivity | PASS |
| Synthetic Delta Silver validation | PASS |
| dbt Gold models and tests | PASS |
| Incremental and restart persistence | PASS |
| Resource safety | PASS (dbt peak UNVERIFIED) |
| Regression checks | PASS |
| Independent analytics qualification | PASS |
| Bronze → Spark → Silver → Gold | BLOCKED |
| Full Module II rehearsal | BLOCKED |
| Cloud / production readiness | UNVERIFIED |
