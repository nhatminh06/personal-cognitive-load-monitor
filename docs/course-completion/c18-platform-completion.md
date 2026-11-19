# C18 platform completion

**Date:** 2026-11-19

**Starting revision:** `52c6666dd520139057528c934b5664e2800f9bae`

**Overall decision:** **BLOCKED — database locally qualified; platform runtime incomplete**

## Implemented and executed

C18 implemented the selected alternative database package rather than modifying
the full upstream image again. The build starts from an immutable Oracle Linux
base, installs the signed official
`mysql-community-server-minimal-8.4.13-1.el9` RPM, copies only the entrypoint
from KFP's pinned official MySQL image, and initializes KFP's exact three
databases with the entrypoint's native SQL mechanism. The container runs as the
RPM-created `mysql:mysql` user (27:27), with a read-only root filesystem in the
acceptance run. MySQL Shell, OCI Python and a Python executable are absent.

The exact local candidate is
`sha256:367c695a6870d1fed993457575846f13071ea3c8cee88d54a311251ff4dbf0f3`.
Trivy 0.76.2 detected Oracle Linux 9.8, inventoried 115 SPDX packages, and
reported 0 HIGH and 0 CRITICAL findings using the database updated at
`2026-11-19T13:02:29.533007734Z`. The unsuppressed raw scan SHA-256 is
`b056d612e5a93a08961e555e1022d117abbc3ee6d4a1aa935c442fa011b324dc`;
the SPDX JSON SHA-256 is
`f48d812bf3c9f96d081be2ebb86356b9f57096655892cf476e51938d33dfee5b`.
Trivy warned that the verbose Oracle copyright/license string could not be
normalized as an SPDX license expression; it still emitted the complete package
inventory. This is an SBOM-format limitation, not a hidden package or scan pass.

A task-owned, 1 GiB/1 CPU container completed initialization and authenticated
startup. `cachedb`, `metadb`, and `mlpipeline` existed; a wrong password was
rejected; a migration fixture survived container restart; `CHECK TABLE` returned
`OK`; and exact readback returned `(1, persisted)`. Maximum observed memory was
436.3 MiB and the persistent volume held 218,427,673 bytes. The task-owned
container and volume were removed after evidence capture. Both kind clusters
were untouched.

The first runtime attempt exposed and corrected two packaging/invocation facts:
Oracle's RPM uses UID/GID 27 rather than upstream image UID/GID 999, and a shell
initializer cannot call the parent entrypoint's private function. The final
image uses the correct UID and a native `.sql` initializer. KFP's MySQL
Deployment must therefore patch `runAsUser`, `runAsGroup`, and `fsGroup` to 27.

## Completion contract

| Stage | Status | Current evidence or exact blocker |
|---|---|---|
| Kafka to Bronze | IMPLEMENTED / historical local runtime | Production bulk-ingestion and recovery contracts exist; no fresh C18 run was needed. |
| Spark/Delta | BLOCKED | SEC-022 image is local-development-only and cannot satisfy the mandatory image gate. |
| Trino/dbt | BLOCKED downstream | Qualified images exist, but no qualified C18 Silver output can be consumed. |
| Airflow/Flink | STATICALLY VERIFIED / historical local runtime | Existing bounded tests and evidence retained; not rerun as a substitute for the blocked data slice. |
| KFP database | LOCALLY INTEGRATED | Exact image scan, init, auth, persistence, restart and integrity passed. |
| KFP/MLflow/artifacts | BLOCKED | Metadata writer/envoy, MLMD, artifact store and MLflow identities remain unqualified; local images are unpublished/unsigned; no isolated runtime authorization or 12 GiB headroom. |
| KServe/FastAPI | IMPLEMENTED / not freshly deployed | Source and local application-image qualifications exist; model approval, remote immutable images and authorized cluster mutation are absent. |
| Knative/anomaly | PASS_LOCAL / cloud runtime BLOCKED | Durable application state/recovery tests exist; no qualified durable Broker transport or authorized controller deployment. |
| GKE/GCS | NOT RUN | Provisioning, billing, registry publication and Kubernetes mutation were not authorized. |
| 100 GB benchmark | NOT RUN | The weighted rubric does not independently require it; the repository's additional target still requires a dedicated host and actual byte reconciliation. |

The existing C10 report validator and C11 fail-closed preflight remain the
canonical acceptance interface. No second orchestrator was added. Their runtime
path cannot honestly advance until the remote image ledger, controller matrix,
owner authorization, explicit kubeconfig and minimum 12 GiB available-memory
gate pass. The current laptop measured roughly 7.1–7.6 GiB available during
C18, so Gate 2 must run on the specified dedicated host (8 vCPU, 32 GiB RAM,
12 GiB available, and 150 GiB genuinely free storage) or equivalent.

## Validation

- Focused database, KFP and acceptance tests: 41 passed.
- Full regression: 677 passed, 5 skipped, 5 warnings; 83.76% coverage (81% required).
- Ruff: passed.
- Scoped MyPy: 25 source files passed with explicit package bases and missing
  third-party stubs ignored, matching the repository's established scope.
- Six-component KFP v2 compilation: passed; generated package SHA-256
  `fc8622c1d5087985b843e62b95de3d96b26680d119360a00817b4113d15d49ee`.
- Helm lint and render: passed (informational icon recommendation only).
- Terraform format: passed. Provider-backed validation was blocked because the
  pinned Google provider 5.45.2 is not present in the local cache; no network or
  cloud operation was authorized.
- Git whitespace validation: passed.

## Next executable stage

Publish this exact qualified database image under an immutable registry digest,
sign it, attach the recorded SBOM and genuine provenance, and rescan the remote
digest. In parallel, finish the remaining KFP metadata/artifact-store/MLflow
image ledger. With separate owner authorization and a non-protected host meeting
the C11 resource gates, render the KFP 2.18.1 overlay with UID/GID 27 and execute
the six-component negative-input and positive training runs. A real KFP run ID,
MLflow identity and independently retrieved artifact-tree digest are the next
runtime acceptance outputs. No C2.2 model approval is implied.
