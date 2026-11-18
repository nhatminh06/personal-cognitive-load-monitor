# C8.1 MinIO qualification and large-data readiness

**Verification date:** 2026-11-18. No service, cluster, cloud resource or
greater-than-100-GB workload was started.

## Decision

**MinIO: NO-GO.** Neither authentic distribution available for evaluation
satisfies the repository's normal zero-HIGH/zero-CRITICAL, supported-runtime,
non-root and reproducibility gates. SeaweedFS remains separate S3-compatible
evidence and is not counted as MinIO.

### Maintained candidate: MinIO AIStor Free

The official AIStor documentation requires an active MinIO Software License.
AIStor Free permits a single compute resource and omits HA and several enterprise
features. No license was supplied or accessed. The official `latest` reference
resolved read-only on 2026-11-18 as follows:

- OCI index: `quay.io/minio/aistor/minio@sha256:107cf2014a9583c74c11e3cdbd6903d89c2244355886b89ce532f4ecae9c23f3`;
- linux/amd64 manifest: `sha256:a94e1fe399bd050fe6d6148839597a4995350c0e62c9e83f0cec8b5630ed0a1e`;
- embedded release: `RELEASE.2026-09-19T17-05-25Z`, source revision
  `b3f01943b83e7975e01233fc613cb5f0941b57d1`;
- supported RHEL 9.8 base, but no configured runtime user (root by default).

Trivy 0.76.2 used vulnerability DB schema 2 updated 2026-11-17 19:04 UTC.
The exact amd64 manifest completed OS and Go scans with **22 HIGH and 0
CRITICAL** occurrences: six OS, seven in `mc`, and nine in `minio`. Findings
include fixable `pcre2`, Go stdlib, `x/net`, `go-jose` and Thrift issues, plus
`CVE-2026-39414` in MinIO without a reported fixed version. Raw JSON SHA-256:
`08d63d939c6d4a91c30798e70ad5f01759679a2248f2e23061c03b4f12866a97`.

Official references: [container installation](https://docs.min.io/aistor/installation/container/install/)
and [AIStor Free licensing](https://docs.min.io/aistor/operations/licenses/#minio-aistor-free-community-use).
The image was scanned remotely by immutable platform digest; it was not loaded
or executed.

### Community MinIO

The upstream repository is archived and explicitly no longer maintained. Its
legacy binaries receive no updates, while current community distribution is
source-only under AGPLv3. The retained authentic local experiment is
`cogniflow-minio:RELEASE.2025-04-22T22-12-26Z`, image ID
`sha256:1fbbfbaf8596ab99dc06d37641d9bbb72073c5e4b4c2daec408f7b26a2d500ba`.
It also has no configured runtime user. A complete scan found an end-of-life
Alpine 3.21.9 base and **68 HIGH / 6 CRITICAL** occurrences. The Critical set
includes MinIO OIDC/LDAP defects and fixed-version gRPC and RabbitMQ library
defects. Raw JSON SHA-256:
`8a3a4373cd5f71fba754be083e848fbadf8b0f7bc672885a7b7f50907c757a84`.

Upstream status and license are recorded in the
[archived MinIO repository](https://github.com/minio/minio). A custom fork that
repairs security defects with no upstream fixed version would no longer be the
smallest maintainable qualification path.

Because the mandatory image and license gates failed, bucket initialization,
write/read checksum, restart, authorization rejection and Spark/Delta tests were
not run. The existing SeaweedFS configuration and evidence were unchanged.

## Greater-than-100-GB readiness

The generator correctly requires explicit execution and separate
`--allow-over-100gb` authorization, writes exact-size partitions, synchronizes
data and manifests, verifies SHA-256/event identities, resumes by independently
rescanning committed data and enforces a free-space reserve.

A fresh bounded probe generated exactly 256,000,000 bytes in four 64,000,000-byte
partitions and 512,794 unique rows. It used 33,888 KiB peak RSS and took 21.297
seconds (12.020 MB/s). A full resume reconciliation took 12.091 seconds (21.173
MB/s). The manifest SHA-256 was
`c6cc37f88dad14e65a2b13e764d2319ae56bb4d4db1d10a4eef8c1fc9980453e`.
The task-owned 256 MB partitions were removed after their checksums were
captured; reports and checksums remain under ignored `build/c81-evidence`.

Linear projection is approximately 200.3 million rows, 2.31 hours to generate
100,000,000,001 bytes, and 1.31 hours for a clean resume scan on this CPU and
filesystem. These are generator-only projections, not processing estimates.

The laptop is unsuitable: it had 4,551,561,216 bytes available RAM initially
(later 3,936,313,344), 11,312,050,176 bytes swap in use, only 83,030,016 bytes
free in `/tmp`, and 126,680,887,296 bytes free on the sole persistent filesystem.
Even the source plus the required 20 GB reserve nearly consumes that disk; it
cannot safely hold Bronze, Delta, shuffle, checkpoints and reconciliation
evidence. Both kind clusters remained untouched.

The smallest defensible execution target is a dedicated, teardown-bound host
with at least 8 vCPU, 32 GiB RAM and **750 GB** of persistent storage. That
allows separate source and Bronze copies, Delta/Gold output, Spark shuffle,
checkpoints/logs and at least 20 GB reserve. Use the checked-in generator command
from `benchmark-plan.md`, a 110,000,000,000-byte hard ceiling, 128 MB partitions,
same-zone networking, 24-hour automatic shutdown and a $50 billing alert.

At current us-central1 list prices, an illustrative 24-hour `n2-standard-8`
plus 750 GB balanced persistent disk and one GKE management fee is approximately
**$14.19** before logging, registry, snapshots, network transfer, managed
services, tax or discounts. This is a planning estimate, not authorization or a
quote. Inputs came from the official [Compute Engine](https://cloud.google.com/products/compute/pricing/general-purpose),
[block storage](https://cloud.google.com/products/block-storage), and
[GKE](https://cloud.google.com/kubernetes-engine/pricing) price pages. Recalculate
in the official pricing calculator immediately before use.

The execution path is still incomplete: the generator produces files but there
is no qualified bulk driver that publishes and accounts for all partitions
through Kafka/Bronze, and the Spark image remains SEC-022 local-only and fails
the normal image gate. A qualifying run must independently record bytes read by
the processing engine, not merely generated bytes, then reconcile source,
Kafka, Bronze, Silver/Delta and Trino/dbt Gold counts and bytes. Flink evidence
must use a declared representative subset if the instructor permits it; otherwise
the full streaming scope needs separate sizing.

## Four cloud deployments

The rubric retains four separately accepted deployments; sharing one authorized
VPC/GKE cluster, Artifact Registry, secret store, logging project and teardown
deadline can reduce cost but cannot collapse their evidence:

1. MinIO/accepted AIStor on GCE or GKE: blocked by the image scan, absent license,
   immutable publication/signing and persistent-volume/IAM acceptance.
2. Flink on GCE/GKE/Dataproc: needs published qualified images, checkpoint
   storage, workload identity, recovery and result evidence.
3. Spark on GCE/GKE/Dataproc: blocked by SEC-022; requires a normally qualified
   Spark/Delta/S3A image and full reconciliation.
4. Airflow on GCE/GKE/Composer: needs persistent metadata, secret/IAM handling,
   six-task execution, retry/recovery and teardown evidence.

Owner authorization must name the project, billing account, $50 benchmark and
separate deployment budget caps, quotas, region, service accounts, approved
images/licenses, 24-hour deadline and deletion scope. No cloud API was accessed.

## Validation

- focused Bronze, behavioral, benchmark and rehearsal contracts: 33 passed;
- Ruff on the focused generator/storage paths: passed;
- both Module II Compose files resolved with `docker compose config -q`;
- full regression was not repeated because application source did not change.

SEC-022, C6 BLOCKED, C7 PASS_LOCAL and M10.3 local PASS remain unchanged.
