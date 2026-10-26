# SEC-022 owner decision packet

- Status: **ACCEPTED RISK — LOCAL DEVELOPMENT ONLY**
- Validation date: 2026-10-25
- Approval date: 2026-10-25
- SEC-022 is accepted, not remediated.

## Recorded decision

Risk owner: repository owner **`nhatminh06`**, verified as authenticated GitHub user ID `118103597` with repository admin permission. Approval is limited to the exact local image and controls below. It does not remediate a CVE, authorize deployment, or permit production data.

- Expiry: **2027-01-23**, 90 days from this validation.
- Reviews: **2026-11-24**, **2026-12-24**, and expiry review **2027-01-23**.
- Allowed: isolated local development, fixed `bronze_to_silver.py`, trusted synthetic data.
- Prohibited: production, staging, GKE/Kubernetes/Helm, public services, arbitrary Spark code, untrusted workloads/data, cloud credentials, or personal/regulated data.

## Exact accepted inventory

- Image: `cogniflow-spark:3.5.5-delta-3.3.2`
- Image ID: `sha256:d55eac37429cb0d94208d79fcae0f1002662b1d9700eb1b4a522bbe6cf2bb0e8`
- Trivy report: `reports/security/spark-3.5.5-trivy.json`
- Report SHA-256: `61184f9ef4446e4ba903e30d17dfd9e0520c5d59d4fcad8c763ca1e71332de9b`
- Ivy manifest SHA-256: `d24d4429eace494986a8330700c5dd36de4a1c0632a9a8b49b9faff7b3526d82`

The report contains the complete occurrence-level package, installed-version, fixed-version and advisory inventory: **126 High/Critical occurrences, 107 distinct IDs, 121 High, 5 Critical, 122 with scanner-reported fixes and 4 without**. The five Critical IDs are:

| ID | Package | Published fix in report | Workflow relevance |
|---|---|---|---|
| CVE-2019-10202 | `jackson-mapper-asl` | none | Legacy transitive component; no approved direct use |
| CVE-2022-46337 | `derby` | 10.14.2.1 / 10.15.2.1 / 10.16.1.2 | Embedded database path not used |
| CVE-2023-44981 | `zookeeper` | 3.7.2 / 3.8.3 / 3.9.1 | ZooKeeper path not used |
| CVE-2024-47561 | `avro` | 1.11.4 | Present in Spark dependency graph; approved job does not ingest Avro |
| CVE-2026-75595 | `netty-handler` | 4.1.137.Final / 4.2.17.Final | Netty is reachable inside local Spark; external access is blocked |

The Ubuntu 20.04 base is EOL. Reachable approved-path components include Spark RPC/shuffle internals, Netty, Spark SQL/Jackson, Parquet/Delta, Hadoop S3A and AWS SDK. Unused components remain present and vulnerable; isolation is compensating control, not proof of non-reachability or remediation.

## Validation evidence

- Six approved JARs were copied from the existing cache into new volume `cogniflow-sec022-validation-spark-ivy`; every checksum matched. The original `cogniflow-module2_spark-ivy` volume was not modified.
- Runtime: UID/GID 185, read-only root and Ivy cache, no privilege/capabilities/Docker socket/published ports, 1792 MiB and 1.5 CPU, bounded tmpfs, internal-only storage/control networks.
- Runtime package resolution uses the six verified local JARs directly. No `--packages` invocation or outbound dependency download occurs.
- Spark read deterministic Bronze through S3A, initialized Delta, wrote Silver, reopened history, and replayed idempotently. Trino returned 2 rows and history `WRITE`, `MERGE`, `MERGE`; dbt passed 15/15 operations/tests.
- The real six-task Airflow DAG succeeded through authenticated fixed Spark/dbt runners. A wrong token propagated HTTP 401 and an unauthenticated request returned 401.
- Empty and hash-tampered caches failed before the runner listened. Public internet lookup failed, and an unrelated internal network could not resolve the runner.
- Pytest: 76 passed, coverage 88.67%; Ruff and MyPy passed; Compose validated; Helm lint/render passed with no Spark/runtime token; Gitleaks found no secret in intended changes.
- Temporary containers and networks were stopped. Named volumes were preserved.

## Mandatory controls and revocation

Every control in `sec-022-development-exception-proposal.md` is mandatory. Approval is automatically revoked by an image/dependency digest change; failed checksum/isolation test; new port, external route, privilege, Docker socket or arbitrary command; Kubernetes/remote use; untrusted data/code; missed 30-day review; expiry; or failure to evaluate a compatible upstream fix within 14 days.

Monitor Spark 3.5 maintenance, Hadoop/S3A, Delta, Netty, Jetty, Jackson, Parquet, JLine, LZ4, AWS SDK, Ubuntu/JDK and the scanner database at each review.

## Required PR #6 description correction

Replace statements that call every occurrence fixable with:

> Spark 3.5.5: 126 High/Critical occurrences (122 with published fixes, 4 without; 107 distinct IDs; 5 Critical). Hardened Spark 3.5.9: 178 (99 with fixes, 79 without). Official Spark 3.5.9: 719 (181 with fixes, 538 without). Official Spark 4.1.3: 720 (184 with fixes, 536 without). The patched dependency proof is non-deployable: 21 occurrences (19 with fixes, 2 without) and failed strict convergence. SEC-022 is ACCEPTED RISK — LOCAL DEVELOPMENT ONLY through 2027-01-23; it is not remediated and does not authorize production deployment.

No PR edit, commit, push, merge, deployment or approval was performed during this validation.

## Approval record

| Field | Value |
|---|---|
| Decision | ACCEPTED RISK — LOCAL DEVELOPMENT ONLY |
| Owner | `nhatminh06` (verified GitHub user ID `118103597`) |
| Approval date | 2026-10-25 |
| Expiry | 2027-01-23 |
| Reviews | 2026-11-24, 2026-12-24, 2027-01-23 |
| Signature/reference | Explicit owner authorization in the SEC-022 release conversation |
