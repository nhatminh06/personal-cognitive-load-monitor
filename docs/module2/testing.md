# Module II verification evidence

## PR #19 isolated end-to-end rehearsal — 2026-10-27

Fresh runtime evidence was captured from Compose project
`cogniflow-rehearsal-pr19-20261027a`. It used a unique network, dynamically
selected loopback ports, fresh credentials, project-owned volumes and small
synthetic fixtures. Spark and Flink were run sequentially. The existing local
Kubernetes cluster, Terraform state, persistent Module II volumes and MLflow
candidates were not read or modified. All rehearsal containers were stopped;
the rehearsal volumes were preserved for inspection.

- FastAPI returned three `202` responses only after Kafka acknowledgements.
  Bronze stored/read back the same three events, replay resolved to the same
  object, and SHA-256 `004bab33ed2ba36afefb5c8ee46c9b936beac87f88e58db903de684e3ddd9eb4`
  covered the stored bytes.
- Spark produced a true Delta table. Two direct runs returned exit 0 and its
  history progressed from `WRITE` to `MERGE`; the later Airflow run performed
  another idempotent merge. Trino returned 3 rows, 3 distinct event IDs and
  Kafka offsets 0–2.
- Two consecutive dbt builds passed 15/15, using incremental `MERGE` models.
  Gold reconciliation returned three accepted Silver events and no stale rows.
- Flink job `59e7d41f969486b4b4401c20935ebd01` ran all five tasks. Its deterministic
  rolling window contained 10 unique events, 800 focus minutes and 410
  distraction minutes. Three duplicate events did not change the oracle.
  Redis rejected a stale write (`0`), and the authenticated feature API returned
  `200` after projecting internal Flink window metadata out of the public model.
- After a TaskManager restart the job returned to `RUNNING` from checkpoint 18;
  the checkpoint API reported one restored checkpoint. One failed checkpoint
  was expected during the deliberate interruption.
- Airflow completed all six real tasks in about 181 seconds: source check,
  validation, Spark, Silver verification, dbt and Gold verification. The DAG
  run and every task state were `success`.

The ignored evidence directory is
`build/module2-rehearsal/pr19-20261027a/`. It contains redacted Compose output,
machine-readable Airflow state, Trino counts, container/resource inventories
and SHA-256 checksums. `.env.secrets` is mode `0600` and is intentionally not
part of the report or Git history.

Final source validation passed **325 Python tests in 44.61 seconds with 88.89%
combined coverage**, Ruff, scoped MyPy and the full isolated Compose render.
The first sandboxed Pytest attempt was stopped because its background-thread
test could not progress under the syscall sandbox; the identical suite passed
outside that restriction. Flink Maven/JUnit was attempted twice with local,
network-disabled images but could not resolve the pinned Jackson 2.18.11
artifacts from either disposable cache, so Java unit tests were not rerun.
Actionlint, Trivy, Gitleaks and DVC were unavailable locally. Existing prior
evidence for those checks is not relabeled as fresh PR #19 evidence.

The final PR #19 source review also verified that `.env.secrets` is created
once with exclusive-create semantics, mode `0600`, flush and filesystem sync;
an existing path is rejected without changing its content. The isolated demo
now has one project-pinned Compose command and a regression guard against the
shared development project and Make targets.

Fresh evidence supports the Kafka, object-storage-equivalent, Spark/Delta,
Trino/dbt, Flink/Redis and Airflow local criteria: **60% before instructor
judgment on SeaweedFS equivalence**. This run does not claim MinIO specifically,
the >100 GB criterion, cloud deployments, HA/load acceptance or production
readiness. The invalid and late streaming fixtures were published, but their
dead-letter topic payloads were not independently consumed during this run.
SEC-022 remains an accepted local-development exception through 2027-01-23,
not a production approval.

Runtime evidence captured 2026-10-24 and revalidated where stated on 2026-10-25:

- Kafka: authenticated API accepted and broker acknowledged real events.
- Bronze: one Kafka event stored/read with topic, partition, offset and checksum.
- Silver: one row; Delta history `0 WRITE`, `1 MERGE`; rerun remained one row.
- Trino: queried the true Delta table and returned ratios `0.75/0.25`.
- dbt: two consecutive runs, each `PASS=15`, six incremental Gold tables.
- Airflow: six-task DAG test completed with state `success`.
- Flink: genuine job ID `004931d4451a5e27e6ae8b6cdf82ba18` reached `RUNNING`.
- Redis/Kafka/API: streaming event returned `0.8/0.2`, timestamp and Flink provenance through all three.

Final local regression: 59 Pytest tests passed; combined Module I/II Python coverage was 87.79%; Ruff passed; MyPy passed for both packages with third-party missing imports ignored; DVC reported all three stages unchanged/cached; all four notebooks executed; Compose validated; and both demo-rule and local-model Docker smoke tests returned `is_fallback=false`. The deterministic tiny generator wrote 10 records / 4,989 bytes with SHA-256 `aa93f7a0a8a1ce51e1a9d3bd4a8a5772a283f86aa985cb8aaf30c2269188a2c2`.

Graphify updated structurally from 281/419/24 to 497 nodes/838 edges/35 communities. Semantic, SQL, and HCL extraction were unavailable. The initial notebook run failed only because the restricted sandbox prohibited local kernel sockets; the approved local rerun executed all four successfully.

Final-hardening evidence on 2026-10-24:

- Python: 64 tests passed; combined coverage 89.74%; Ruff passed.
- Java: the Flink image build ran Maven/JUnit successfully against the shared JSON fixture.
- Spark 3.5.5 / Java 11: `jobs/verify_feature_parity.py` ran the same three fixtures through the real Spark expressions and returned `{"engine":"spark","cases":3,"status":"passed"}`. An initial Python 3.8 incompatibility in the test runner (`zip(strict=...)`) failed visibly and was removed before the passing rerun.
- Flink: job `d092287758b0063f68c6bc46ca122256` ran six operators. The deterministic 10-second window matched the fixture oracle exactly (11 unique events, focus 693, distraction 512, ratios `0.575103734439834/0.42489626556016596`).
- Recovery: after TaskManager restart, the job returned `RUNNING`; checkpoint API reported `restored=1`, eight completed and zero failed checkpoints.
- Redis: the stale timestamp Lua test returned `0` and preserved the newer `15:00:09Z` value.
- Observability: Prometheus reported `up=1` for API, Flink JobManager and TaskManager; Grafana API returned dashboard UID `cogniflow-module2`.
- Resource cleanup: observability was removed and Kafka/Flink/Redis stopped without deleting named volumes. Available host memory after shutdown was 6.6 GiB.
- Graphify 0.9.92 code-only update: 542 nodes, 944 edges, 31 communities. Semantic extraction was unavailable without an approved LLM key; SQL/HCL parsers were not installed, and `serviceaccount.yaml` was conservatively skipped as potentially sensitive.

Batch/Airflow Prometheus exporters and a fresh rerun of every heavyweight batch service remain explicit gaps; earlier real batch evidence above is retained and not relabeled as a new run.

Security-gate rerun on 2026-10-25:

- Airflow 3.3.2 completed all six tasks in 163.24 seconds with LocalExecutor, UID 50000, no Docker socket, and authenticated fixed-command Spark/dbt runners.
- The preserved MinIO volume contained 91 objects / 105,683 bytes. Every object SHA-256 matched after copying to a new SeaweedFS 4.50 volume; the source volume was not altered. boto3 read/write, S3A, Delta MERGE/reopen, Trino, dbt, and replay tests passed.
- dbt-core 1.11.14, dbt-trino 1.10.6, and sqlparse 0.6.0 passed `pip check`, parse, compile, two builds (`PASS=15` each), and eight explicit tests.
- Python: 73 passed with 88.67% coverage; Ruff and MyPy passed. Flink: four JUnit tests passed. DVC and all four notebooks executed.
- At that security gate, Airflow, SeaweedFS, dbt, API, and Flink images had zero fixable High/Critical findings. Spark 3.5.5 had 126 High/Critical occurrences: 122 with reported fixes, 4 without, 107 distinct IDs and 5 Critical; the later owner decision accepts rather than remediates them.
- Later exact-digest scans rejected Spark 3.5.9 (719 occurrences: 181 with fixes and 538 without; 699 distinct, 29 Critical) and Spark 4.1.3 (720: 184 with fixes and 536 without; 685 distinct, 27 Critical). No unverified candidate replaced Spark 3.5.5.
- The isolated SeaweedFS topology preserved authenticated S3 access and bucket inventory (Bronze 1 object, lakehouse 141 objects) while a default-network client could not resolve `seaweedfs:9333`.

SEC-022 exception validation on 2026-10-25 used only new disposable volumes. Six approved Ivy JARs matched the manifest, and the cache remained read-only. Spark ran without runtime Ivy resolution, read two deterministic Bronze records through S3A, wrote/reopened Delta, and replayed twice without increasing the row count; Trino returned two rows with Delta history `WRITE`, `MERGE`, `MERGE`. dbt passed 15/15 and the real six-task Airflow DAG succeeded; wrong/missing tokens, missing/tampered JARs, public internet access and unrelated-network access all failed closed. The final Python regression was 76 passed at 88.67% coverage; Ruff, MyPy, Compose, Helm and Gitleaks passed, and DVC reported the pipeline up to date. Temporary services and networks were stopped without deleting named volumes. This validates compensating controls only; SEC-022 remains unpatched and is accepted for isolated local development only through 2027-01-23.

## Rubric-compliance source review

On 2026-10-27 America/Chicago, the benchmark scalability source review passed
**316 Python tests** in 46.45 seconds with **88.76% combined coverage** against
the 81% gate; Ruff and scoped MyPy passed. The 14 focused recovery tests cover crashes after
partition synchronization, partition publication, manifest synchronization
and manifest replacement, plus incomplete manifest writes, untrusted counters,
missing/tampered partitions, concurrent generators, no-overwrite behavior and
instrumented linear partition verification. Eight 5,000-byte partitions caused
eight normal-path verification calls; a resume scanned all 40,000 committed
bytes once.
The 12,345-byte fixture produced three exact-size partitions and reconciled
physical bytes, manifest totals, event counts, unique event IDs and next-index
progression. Earlier GitHub evidence for commit `8bf85aa` remains recorded as
306 tests with Ruff and GitGuardian passing; it does not describe this commit.

Scoped MyPy (with third-party imports ignored), both Compose configurations,
Terraform formatting, Helm lint/render with synthetic non-production digests,
and KFP compilation passed. Read-only DVC status ran and reported the existing
`data/processed/module3/training_manifest.json` dependency as modified; it was
not reproduced or changed. Terraform validation was attempted but the installed
Google provider could not start in this sandbox, so it did not complete.
Actionlint, Trivy and Gitleaks were unavailable locally.

Maven/Flink JUnit, Spark, dbt and Airflow were not rerun because starting them
could touch preserved development volumes or cross the isolated Spark boundary.
No >100 GB run, MinIO/AIStor runtime, cloud operation or Kubernetes deployment
occurred. Historical runtime evidence above remains evidence for its recorded
environment and commit, not a fresh execution claim.
