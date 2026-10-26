# SEC-022 development-only exception proposal

Status: **ACCEPTED RISK — LOCAL DEVELOPMENT ONLY**. SEC-022 is accepted, not remediated. This exception does not authorize production use.

## Scope and inventory

The proposal applies only to local image `cogniflow-spark:3.5.5-delta-3.3.2`, image ID `sha256:d55eac37429cb0d94208d79fcae0f1002662b1d9700eb1b4a522bbe6cf2bb0e8`.
The exact-digest report is `reports/security/spark-3.5.5-trivy.json`:

- 126 High/Critical occurrences representing 107 advisory IDs;
- 122 occurrences with a scanner-reported fixed version and 4 without one;
- 5 Critical occurrences;
- 39 Ubuntu, 81 Java-archive and 6 Python occurrences.

The rejected hardened Spark 3.5.9 candidate contains 178 occurrences: 99 with a reported fix and 79 without one. The non-deployable patched dependency proof contains 21 occurrences: 19 with a reported fix and 2 without one, and failed strict Maven convergence. Neither candidate is an approved runtime.

## Reachability

Spark RPC/shuffle Netty, Spark SQL Jackson, Parquet/Delta, compression codecs, Hadoop S3A and the AWS SDK execute on CogniFlow's batch path. The embedded Spark web server is active even though no UI port is published. YARN, Mesos, Derby, ZooKeeper, Hive/Thrift server paths and Delta's DynamoDB commit coordinator are not used by the approved local workflow, but remain present and are not treated as remediated.

## Allowed and prohibited use

Allowed under this time-limited exception:

- isolated local development on an owner-controlled workstation;
- the fixed `bronze_to_silver.py` job through the authenticated allowlisted runner;
- trusted, synthetic CogniFlow development data in the local S3-compatible store.

Prohibited:

- production, staging, GKE, Kubernetes, Helm or any remote deployment;
- public Spark UI, RPC, shuffle, runner or debugger exposure;
- arbitrary Spark code, notebooks, plugins, packages, workloads or untrusted data;
- cloud credentials, production secrets or regulated/personal datasets;
- representing SEC-022 as fixed or the image as generally safe.

## Mandatory compensating controls

All controls are required; failure of one revokes the exception:

1. Spark starts only through the explicit local Compose `batch` profile.
2. It runs as non-root `spark`, without privileged mode, added capabilities, Docker socket, host networking or published ports.
3. The root filesystem is read-only. Writable locations are bounded tmpfs mounts; the repository and approved Ivy cache are read-only.
4. CPU is limited to 1.5 cores and memory to 1792 MiB.
5. Internal Docker networks restrict Spark to the S3 gateway and authenticated orchestration control plane; Spark has no external route.
6. `JOB_RUNNER_TOKEN` is mandatory, non-default, generated per local session and never committed. The runner exposes only the fixed Spark command.
7. `spark-ivy` must be populated separately using the exact approved dependencies. Every jar must match `infra/module2/spark/ivy-manifest.sha256` and `reports/security/sec022-feasibility/ivy-runtime-trivy.json` before it is mounted read-only. Missing artifacts must fail; network retrieval is not an allowed fallback.
8. Only trusted synthetic development data may be processed.
9. The exact image and artifact inventory are rescanned at every review and after any image, dependency, Compose or job change.

On 2026-10-25 the manifest was copied into a newly created disposable volume, all six JAR hashes were verified, and Spark completed the approved job with the cache mounted read-only and both attached networks marked internal. Runtime startup now verifies the manifest before accepting work, and the fixed command uses the verified local JARs directly rather than `--packages`, so Ivy cannot download or write resolution metadata. Empty and hash-mismatched caches both failed before the runner listened. The existing `cogniflow-module2_spark-ivy` volume was not modified.

## Ownership, expiry and review

- Risk owner: **repository owner `nhatminh06`**, verified as the authenticated GitHub identity (user ID `118103597`) with repository admin permission.
- Approval date: **2026-10-25**.
- Expiry: **2027-01-23**.
- Reviews: **2026-11-24**, **2026-12-24**, and **2027-01-23**, plus before use after an upstream security update.
- Approval record must contain the approver, date, image digest, Trivy database date, Ivy-manifest digest, accepted inventory and next review date.

Automatic revocation conditions:

- image digest or resolved dependency set changes;
- a compensating control is removed or fails verification;
- Spark is added to Kubernetes, Helm, CI deployment or a non-development profile;
- a port, host network, Docker socket, privilege or external network path is added;
- untrusted data/code or non-local credentials are introduced;
- a compatible upstream fix is not evaluated within 14 days;
- the review or expiry date is missed.

## Upstream monitoring

Monitor Apache Spark 3.5 maintenance, Hadoop client-runtime/S3A, Delta 3.3, Parquet, Jetty, Netty, Jackson, JLine, LZ4, AWS SDK and the OS/JDK base. Re-run both image and resolved-artifact scans; a clean image scan alone is insufficient.

## Approval record

The repository owner explicitly approved this exception on 2026-10-25 after technical validation passed. The accepted inventory remains 126 High/Critical occurrences, including five Critical, with 122 scanner-reported fixes and four without. Approval changes the disposition only; it does not patch the image or close the underlying vulnerability risk.

At approval time, PR #6's description incorrectly called all 126 baseline, 178
hardened, 719 official-3.5.9 and 720 official-4.1.3 occurrences fixable. Its
description must use the fixed/unfixed counts recorded above before merge.

| Field | Value |
|---|---|
| Decision | ACCEPTED RISK — LOCAL DEVELOPMENT ONLY |
| Named owner | `nhatminh06` (GitHub user ID `118103597`) |
| Approval date | 2026-10-25 |
| Expiry | 2027-01-23 |
| Inventory/manifest digest | Trivy report `61184f9e…`; Ivy manifest `d24d4429…` |
| Signature or review reference | Explicit owner authorization in the SEC-022 release conversation |
