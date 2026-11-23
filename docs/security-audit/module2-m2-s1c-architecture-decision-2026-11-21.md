# Module II M2-S1C — Spark Architecture Decision

**Date:** 2026-11-21
**Decision:** `DEFER_SPARK`
**Scope:** architecture decision only; no image build or execution, dependency change,
Spark workload, cloud operation, or production qualification was performed.

## Executive decision

Defer real Spark integration while preserving the current Spark-facing contracts.
Spark 4.2.1 with Delta Lake 4.4.0 is the only credible evolutionary path, but it is
not yet a safe migration target for CogniFlow: no exact candidate image has passed
the repository's zero-HIGH/zero-CRITICAL gate, Delta 4.4.0 is built and tested against
Spark 4.2.0 and Hadoop 3.4.2 rather than the proposed Spark 4.2.1/Hadoop 3.5.0
combination, and the S3A commit behavior changes require object-store qualification.

A Polars/delta-rs replacement is technically plausible, but it is a redesign rather
than a security patch. DuckDB alone cannot preserve the current event-key `MERGE`
semantics. Replacing Spark now would transfer transaction, object-store locking,
schema, protocol, and parity obligations into CogniFlow without evidence that this is
safer or cheaper to maintain.

Deferral does not qualify Spark or full Module II. It keeps the demonstrated Airflow
mock and Trino/dbt boundaries intact while an exact Spark 4 candidate is evaluated
independently.

## A. Repository requirements

### Processing and storage contract

The production batch job is `jobs/bronze_to_silver.py`. It requires:

- strict session and behavioral input schemas, schema-version checks, timestamp and
  numeric validation, Kafka provenance fields, and deterministic rejection handling;
- JSON Bronze reads from `s3a://.../bronze/session_events/` plus driver-side behavioral
  event loading through the repository S3 client;
- DataFrame transformations for focus/distraction ratios, event dates, canonical
  column projection, and duplicate removal;
- incremental Delta writes to `silver.session_features` and
  `silver.behavioral_features` using event-key `DeltaTable.merge`, with create-on-first-
  write and `event_date` partitioning;
- idempotency on `event_id` (and `event_id, window_id` for behavioral records), Delta
  history inspection, physical-byte accounting, persisted intermediate frames, and a
  machine-readable completion-evidence contract;
- UTC behavior and local resource bounds (`local[1]`, one GiB driver memory, one
  shuffle partition) for the isolated local scope.

The job configures Delta's Spark SQL extension/catalog and Hadoop S3A with a custom
endpoint, path-style access, explicit credentials, and the S3A filesystem
implementation. These settings are architectural requirements for the present local
SeaweedFS/MinIO-style object-store path, not incidental image contents.

### Orchestration and downstream contracts

`dags/cogniflow_bronze_to_gold.py` preserves the six-stage order:

`check_source -> validate_input -> spark_bronze_to_silver -> verify_silver -> dbt_build -> verify_gold_quality`

The Spark stage is invoked through the authenticated internal runner. The runner in
`jobs/internal_job_runner.py` uses an allowlisted `spark-submit` command and verifies
a fixed Ivy manifest before launch; it does not resolve arbitrary packages at runtime.
The current manifest includes Scala 2.12-era Delta 3.3.2, Hadoop AWS 3.3.4, AWS SDK
v1 1.12.262, ANTLR, and WildFly OpenSSL artifacts. A Spark 4 migration therefore
requires a newly resolved and checksummed manifest rather than an in-place JAR swap.

Trino reads `lakehouse.silver.session_features`; dbt staging preserves its columns and
six incremental gold models use Trino `MERGE`. Existing schema tests depend on unique
and non-null event identifiers, non-null session identifiers, and schema version 1.0.
The Silver table names, column types/nullability, partitioning behavior, Delta protocol
readability, and repeat-run results are downstream compatibility boundaries.

### Relevant verification surface

The repository already checks the fixed runner command and manifest, DAG edges and
runner endpoints, non-root/read-only/local-only Compose isolation, resource limits,
historical Delta-version selection, feature parity, behavioral offline/online parity,
and Module II evidence reconciliation. A future runtime qualification must retain
those checks and add migration-specific Delta, S3A, and Spark SQL behavior tests.

This inventory was derived from direct inspection of the job, DAG, runner, Compose,
dbt models/tests, and focused tests. A deterministic repository symbol graph was used
as a cross-check; generated graph cache is ignored and does not alter production code.

## B. Spark 4 migration feasibility

### Proposed version matrix (not approved for production)

| Component | Proposed version | Evidence and status |
|---|---:|---|
| Apache Spark | 4.2.1 | Requested supported line; upstream POM inspected |
| Delta Lake | 4.4.0 | Supports Spark 4.0/4.1/4.2 shims; exact Spark 4.2.1 pairing remains unverified |
| Scala | 2.13 | Spark 4.2.1 uses 2.13.18; Delta 4.4.0 builds with 2.13.17. Binary line agrees, exact closure must be resolved |
| Java | 17 | Spark 4.2.1 requires Java 17 (upstream specifies at least 17.0.11) |
| Python | 3.10+ | Spark 4 supports 3.10+; exact maintained runtime must be pinned and scanned |
| Hadoop runtime | 3.5.0 | Owned by Spark 4.2.1 runtime; not replaced with Delta's build-time 3.4.2 |
| Hadoop AWS/S3A | 3.5.0-aligned | Must match the Spark-owned Hadoop closure |
| AWS SDK | v2 2.35.4 | Spark POM property; exact transitive modules must be verified |
| Jackson | Spark-owned 2.21.2 BOM | Delta's Spark 4.2 build logic references 2.18.2; convergence and binary tests required |
| Netty | 4.2.13.Final | Spark POM property; final dependency graph and scan required |
| Avro | 1.12.1 | Spark POM property; final dependency graph and scan required |
| Derby | 10.16.1.1 | Spark POM property; determine whether removable for this runtime |
| ZooKeeper/Curator | 3.9.5 / 5.9.0 | Spark POM properties; determine whether required by selected runtime profile |

Sources: [Spark 4.2.1 POM](https://github.com/apache/spark/blob/v4.2.1/pom.xml),
[Delta 4.4.0 build](https://github.com/delta-io/delta/blob/v4.4.0/build.sbt), and
[Delta cross-Spark definitions](https://github.com/delta-io/delta/blob/v4.4.0/project/CrossSparkVersions.scala).

### Hadoop 3.5.0 versus 3.4.2

The version difference is real but is not, by itself, proof of an invalid runtime.
Delta's Spark dependencies are `provided`: Spark supplies Spark and Hadoop at runtime.
The Delta storage build also marks Hadoop common/AWS dependencies as provided and
documents that users supply the Hadoop line, while warning that S3A APIs have had
incompatible changes. Delta's Hadoop 3.4.2 property is consequently evidence of its
build/test baseline, not an instruction to inject Hadoop 3.4.2 JARs into Spark 4.2.1.

The safest proposed closure is one Spark-owned Hadoop 3.5.0/S3A/AWS SDK set, with no
parallel Hadoop 3.4.2 or AWS SDK v1 closure unless a required, documented component
proves otherwise. Compatibility remains unconfirmed until the exact artifact graph is
resolved and the repository's custom endpoint is tested after the image security gate.

### Migration changes and risks

The job's core DataFrame and Delta merge APIs still have direct successors, so an
application rewrite is not presently indicated. Required changes would nevertheless
include Scala 2.13 artifact coordinates, Delta 4.4 artifacts, a new deterministic Ivy
manifest, Java/Python base runtimes, and any configuration changes proved necessary by
Spark 4 behavior.

Confirmed upstream changes relevant here include:

- Python 3.8 is unsupported in Spark 4; later 4.x releases also raise pandas, NumPy,
  and PyArrow floors and change Arrow conversion behavior
  ([PySpark migration guide](https://spark.apache.org/docs/4.2.1/api/python/migration_guide/pyspark_upgrade.html)).
- Spark 4.1+ defaults S3A to the Hadoop Magic Committer for S3 buckets, which can alter
  write/commit behavior against the local compatible object store
  ([core migration guide](https://spark.apache.org/docs/4.2.1/core-migration-guide.html)).
- Spark SQL behavior changes across major versions require explicit schema, timestamp,
  nullability, deduplication, and expression parity tests
  ([SQL migration guide](https://spark.apache.org/docs/4.2.1/sql-migration-guide.html)).

Security feasibility is unknown. Newer dependency versions reduce known legacy
exposure but do not establish a zero-HIGH/zero-CRITICAL image. The prior failed Spark
3 candidates demonstrate why version recency cannot substitute for an exact scan.

**Assessment:** credible future candidate, not migration-ready and not security-cleared.

## C. Spark-independent alternative feasibility

### DuckDB

DuckDB's Delta extension supports local/remote reads, table creation, append, S3,
checkpoints, and time travel, but currently does not support Delta `UPDATE`, `DELETE`,
or `MERGE INTO`. It therefore cannot by itself preserve CogniFlow's event-key upsert
and repeat-run idempotency contract
([DuckDB Delta extension](https://duckdb.org/docs/extensions/delta)). Extension
autoload/download behavior would also need to be eliminated or reproducibly pinned.

### Polars plus delta-rs

delta-rs exposes Delta merge/update/delete/write operations and accepts Arrow data;
Polars delegates Delta writes and merge behavior to delta-rs
([delta-rs table API](https://delta-io.github.io/delta-rs/latest/api/delta_table/),
[merge API](https://delta-io.github.io/delta-rs/latest/api/delta_table/delta_table_merger/),
[Polars Delta writer](https://docs.pola.rs/api/python/stable/reference/api/polars.DataFrame.write_delta.html)).
This makes the combination functionally plausible for the current single-process,
local-volume workload.

It does not make the replacement equivalent without qualification. The redesign would
have to replace Spark expressions and schemas, prove nullable/timestamp/numeric parity,
recreate merge/history/evidence semantics, pin a Delta protocol that Trino can consume,
and prove failure-safe concurrent writes. delta-rs documents external locking for S3;
DynamoDB is its locking provider, while compatible stores may use conditional `PUT`
with ETags. CogniFlow must prove that the actual local S3-compatible service implements
the required atomic semantics. Unsafe rename mode is not acceptable
([delta-rs S3 locking](https://delta-io.github.io/delta-rs/latest/usage/writing/writing-to-s3-with-locking-provider/)).

Affected interfaces and required acceptance tests would be:

- Bronze JSON and behavioral-event readers: malformed input, schema, provenance, and
  rejection parity;
- transformation output: golden rows for ratios, dates, timestamps, nulls, numeric
  boundaries, deduplication, and duplicate-window behavior;
- Delta writer: first write, update/insert merge, repeat-run idempotency, partitioning,
  transaction history, crash recovery, concurrent writer conflict, and protocol;
- object storage: endpoint/authentication, path style, conditional writes, retries,
  incomplete uploads, and persistence across restarts;
- downstream: Trino schema/readability, dbt seven-model build and tests, repeat
  incremental `MERGE`, and existing evidence reconciliation;
- operations: authenticated Airflow runner invocation, resource limits, non-root
  runtime, exact dependency scan, and no unapproved endpoint access.

**Assessment:** possible redesign, but not evidence-backed as the safest immediate
security remediation. DuckDB alone is functionally insufficient; Polars/delta-rs would
create a large new project-owned compatibility surface.

## D. Deferral implications

Deferral means Spark remains blocked, no real Bronze-to-Silver path is qualified, and
full Module II remains unverified. It avoids executing an image that violates policy,
mixing unproved Hadoop closures, or rewriting the transaction layer prematurely.

Work that can safely continue within already demonstrated boundaries includes:

- pure validation, schema, contract, and golden-fixture tests that do not start Spark;
- Airflow authentication/retry/orchestration tests against owned mocks;
- Trino/dbt analytics work against controlled Silver fixtures, clearly labelled as
  independent of a real Spark producer;
- evidence-schema and reconciliation checks, including failure-path tests;
- read-only upstream dependency monitoring and exact candidate bill-of-materials work;
- design of implementation-neutral Bronze/Silver acceptance datasets without changing
  the production job.

None of that evidence may be promoted to a Spark execution or full-integration pass.

## E. Decision matrix

`Confirmed` identifies repository or upstream source evidence. `Assumption` identifies
an outcome that needs a future experiment.

| Criterion | Spark 4 migration | Spark-independent redesign | Defer Spark |
|---|---|---|---|
| Security feasibility | **Unknown.** Exact image unscanned; dependency modernization is confirmed, gate result is not | **Unknown.** Smaller runtime may help (assumption), but native/Python/extension closure still requires exact scans | **Safe boundary confirmed:** no blocked runtime is executed; does not solve Spark |
| Dependency compatibility | Spark/Scala line aligns; exact Spark 4.2.1 + Delta 4.4.0 + Hadoop 3.5.0 closure unverified | Delta operations exist, but protocol, Trino, S3 locking, and schema parity unverified | No new dependency conflict |
| Functional compatibility | Likely high from retained APIs (assumption); migration behavior tests required | Partial: DuckDB lacks merge; Polars/delta-rs plausible but requires full parity proof | Existing mocks/analytics remain; real Bronze-to-Silver unavailable |
| Engineering effort | High: image, graph, manifest, migration, security and integration qualification | Very high: processing and transaction implementation replaced | Low immediate effort; qualification work is postponed, not removed |
| Long-term maintenance | Upstream-aligned if qualified; large Java closure remains | Smaller engine possible, but CogniFlow owns more cross-engine compatibility | Low short-term; growing version gap and upstream monitoring burden |
| Reproducibility | Achievable with digests/checksums/locked JAR graph; not demonstrated | Achievable with locked wheels/native artifacts/extensions; not demonstrated | Existing qualified mock/analytics scopes remain reproducible |
| CI/resource requirements | High relative to alternatives; JVM/image/security plus object-store tests | Medium assumption; still needs native, Delta, object-store and Trino matrices | Low for independent work; no genuine Spark CI coverage |
| Architectural disruption | Medium: runtime and dependency major-version migration | High: execution and Delta transaction implementation replaced | None now; Module II completion remains blocked |

## F. Recommended option

### `DEFER_SPARK`

This is the safest and most maintainable decision at the present evidence boundary.
It is reversible, preserves downstream contracts and prior independent qualifications,
and does not trade a known policy failure for an unscanned major-version runtime or an
unqualified transaction-layer rewrite.

`MIGRATE_SPARK_4` is rejected **for implementation now**, not rejected as the likely
future direction. Its exact runtime has no passing scan, the exact Delta/Spark patch
pair and Hadoop/S3A behavior are unproved, and migration correctness has not been
tested.

`REDESIGN_WITHOUT_SPARK` is rejected because DuckDB cannot preserve merge semantics and
the viable Polars/delta-rs combination requires broader architectural and correctness
qualification than a runtime migration. There is no current evidence that this larger
change improves the zero-vulnerability outcome.

## G. Remaining blockers

- No exact Spark 4.2.1/Delta 4.4.0 candidate image has passed fresh OS, Java, and Python
  dependency scans with zero HIGH and zero CRITICAL findings.
- The exact published Java closure, duplicate/conflicting artifacts, and Delta artifact
  compatibility with Spark 4.2.1 have not been established.
- Hadoop 3.5.0 S3A and Magic Committer behavior has not been qualified against the
  repository's actual local object store.
- Jackson convergence and other Spark-owned versus Delta-tested version differences
  have not passed binary/runtime tests.
- Python, Java, base OS, image architecture, non-root permissions, and reproducible
  download provenance remain to be selected and verified.
- No real current Spark execution, Delta write/read cycle, persistence test, or end-to-
  end Module II run has passed.

## H. Exact next milestone

**M2-S1D — Isolated Spark 4.2.1 / Delta 4.4.0 Security Candidate Qualification**

1. Resolve and retain the exact published Spark 4.2.1, Delta 4.4.0, Hadoop 3.5.0/S3A,
   AWS SDK, Jackson, Netty, Avro, Derby, ZooKeeper, and transitive dependency graph;
   explain every override or duplicate and make no production manifest change.
2. Select a maintained Java 17/Python 3.10+ minimal base and verify all downloads,
   signatures/checksums, image digest, architecture, SBOM, and deterministic build
   inputs in an isolated disposable candidate.
3. Scan the exact final image. Require zero HIGH and zero CRITICAL findings across OS,
   Java, and Python inventories before any image execution.
4. If and only if the security gate passes, verify non-root filesystem/UID properties.
   Stop at `SECURITY CANDIDATE PASS`; do not run Spark jobs in that milestone.
5. Schedule a separate migration-compatibility milestone for S3A, Delta merge,
   persistence, data parity, Trino/dbt consumption, and Airflow integration.

Until M2-S1D passes, Spark remains **BLOCKED**, full Module II remains **UNVERIFIED**,
and cloud, Kubernetes, and production remain **NOT QUALIFIED**.
