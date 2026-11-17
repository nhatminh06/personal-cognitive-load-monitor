# C3 Module II completion check — 2026-11-17

Starting `main` commit: `7ba056cab9a728060a4ac34edce43f340f7ddeaa`.
This record is committed with its evidence-index update. Both existing kind
clusters were untouched. No new infrastructure, cloud deployment, image publication,
100 GB workload or private Track B evidence was used. M10.3 NO-GO and SEC-022
remain in force.

## Weighted status and fresh evidence

The [grading matrix](grading-matrix.md) remains the authoritative Module II map.
The 10% MinIO product criterion is unresolved. Trino, Delta, Spark, Kafka, Flink
and Airflow carry historical local runtime evidence (60% combined); C3 adds
contract regression, not new live service acceptance. Four cloud deployments (20%)
and strictly >100,000,000,000 processed bytes (10%) remain uncompleted. Source
files and static Compose validation do not earn runtime credit.

| Fresh C3 check | Result |
|---|---|
| Module II contract selection | 72 passed: Bronze, event generation, feature parity, historical/online features, Trino history, job runner, rehearsal isolation, benchmark safety, Spark isolation and Kafka smoke contracts |
| Compose `config -q` | Passed; parsing only |
| Ruff `check src scripts jobs dags` | Passed |
| Scoped MyPy `src/preprocessing_api src/cogniflow_data` | Passed, 22 files |
| Full Python suite / nine-package 81% gate | 623 passed, 5 skipped, 5 warnings in 69.77s; 87.20% coverage (81% gate passed) |
| Live Kafka/Spark/Delta/Flink/Airflow/Trino/dbt | Not run in C3; historical service evidence is in [testing.md](testing.md) |

At inspection, host memory was 15 GiB physical, about 4.4 GiB available, with
8.8 GiB swap used; disk free was 159 GiB. The existing isolated rehearsal preflight
requires at least 6 GiB available RAM and 10 GiB disk. C3 therefore did not start
its Compose profiles or disturb either cluster. The next local runtime pass needs a
host meeting that unchanged resource gate, a unique `cogniflow-rehearsal-*` project,
private credentials, and the existing checked SEC-022 Spark exception restricted to
local development. Execute the existing [rehearsal procedure](testing.md) there;
inspect all service outputs and stop only its own project afterward.

## Object storage decision

SeaweedFS 4.50 currently serves S3 through the Compose service named `minio` for
compatibility with boto3, Spark S3A and Trino endpoint contracts. Historical evidence
covers bucket creation, authenticated read/write, checksum, restart and downstream
processing. No instructor acceptance of SeaweedFS as the rubric's **MinIO product**
was found. Do not label the 10% criterion complete.

The archived MinIO OSS repository is no longer maintained. Its upstream points to
AIStor Free, a maintained single-node offering with a license, and AIStor Enterprise.
The smallest safe implementation is an **isolated optional storage endpoint** once an
instructor accepts AIStor Free as MinIO credit and a reviewed license/image digest
passes the zero-HIGH/zero-CRITICAL gate. The existing `MINIO_ENDPOINT`/S3A/Trino
S3 compatibility seams can target that endpoint with a distinct Compose project,
volume and credentials. Existing SeaweedFS data and service remain intact. No image
or license was available to pin and scan in C3, so adding a runnable AIStor profile
now would create an unqualified path. The local code needs no storage adapter change.

Sources: [MinIO archived repository](https://github.com/minio/minio) and
[AIStor tiers](https://www.min.io/pricing). Product equivalence remains the
instructor's decision, not a technical inference.

## Large-data benchmark readiness

The existing [benchmark plan](benchmark-plan.md) and
`generate_module2_benchmark.py` already require explicit `--execute` and
`--allow-over-100gb` for a target above 100,000,000,000 bytes. The smallest qualifying
target is **100,000,000,001 bytes**, with a separately reviewed byte ceiling, at
least 20 GB free-space reserve, bounded 128 MB partitions, seed/schema/commit/image
identities, per-partition SHA-256/rows, crash-safe manifest, resume verification,
peak RSS, elapsed time and cleanup. The generator never claims full processing.

A future authorized isolated run must reconcile measured source, Kafka ingestion,
Bronze object bytes/rows, Spark/Delta Silver rows/history, Trino/dbt Gold and selected
Flink outputs, with duplicate/invalid/late counts and wall time/resource/cost logs.
Stop on missing or mismatched partitions, free-space reserve breach, count mismatch
or exceeded budget; export sanitized metrics before deleting only benchmark-owned
resources. **No 100 GB run occurred in C3.** The current shared host fails the
rehearsal memory preflight and is unsuitable for that run.

## Four separate cloud acceptance items

[Cloud-deferred mapping](cloud-deferred.md) lists MinIO or accepted AIStor on GCE/GKE,
Flink on GCE/GKE/Dataproc, Spark on GCE/GKE/Dataproc, and Airflow on
GCE/GKE/Composer. Each needs an approved target, distinct workload identity and
namespace/service, immutable scanned image, secrets/IAM, storage/checkpoint or
metadata persistence, health, a real input/output/recovery transcript, bounded
resources, exact artifact ledger, cost and teardown evidence. One local Compose run
cannot stand in for four separately accepted cloud deployments. Spark requires a
replacement image that clears the security gate; SEC-022's image stays local only.
No GCP/API access or deployment occurred.

## Next implementable milestone

Obtain an explicit instructor ruling on SeaweedFS equivalence or AIStor Free credit.
If AIStor is required, obtain its permitted exact image/license and scan results,
then add an isolated optional Compose profile and test S3 read/write plus the existing
Bronze/Spark/Trino contracts on a host with at least 6 GiB available memory. If
SeaweedFS is accepted, rerun the existing isolated rehearsal on such a host and
capture fresh end-to-end service evidence without changing the storage implementation.
