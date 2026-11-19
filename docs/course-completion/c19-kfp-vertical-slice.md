# C19 KFP training and registry vertical slice

**Date:** 2026-11-19

**Starting revision:** `075eb2704521f997a1064eedfaa955ed48fbca1a`

**Decision:** **PARTIAL — artifact durability passed; mandatory metadata and MLflow images blocked**

## Executed integration

The exact KFP 2.18.1 SeaweedFS image
`ghcr.io/chrislusf/seaweedfs@sha256:4b42c212543a0acd4c0e675215ecdcaf62a186ef98def76c7e12701871222d15`
has a complete unsuppressed Trivy 0.76.2 result of 0 HIGH and 0 CRITICAL and
an independently generated SPDX inventory. Its OCI source revision is
`5ef99c1d8dbbeb4a035c055e3b464620506aefac`.

A task-owned container ran as UID/GID 1000 with a read-only root filesystem,
all capabilities dropped, no-new-privileges, 1 CPU and 768 MiB memory. An
authenticated S3 client created `mlpipeline`, wrote and read a 36-byte object,
and verified SHA-256
`09ce944f453750e6386dbbcb48bf2fdecf25f9cded90ff1938898564b712f2f5`.
Wrong credentials were rejected. After restarting the service, the same object
and checksum were retrieved. Peak observed memory was 150.5 MiB. Only the
C19-labeled container, volume and network were removed afterward; both kind
clusters were untouched.

This is real local artifact-store durability evidence. It is not MLflow model
registration, KFP execution, GCS evidence or cloud acceptance.

## Image qualification results

| Role | Exact identity | Result |
|---|---|---|
| MySQL | local `sha256:367c695a…dbf0f3` | Reused C18 0/0 qualification; not rerun |
| Metadata Envoy | `sha256:bf7ad93d…c33126` | 0 HIGH / 0 CRITICAL; non-root binary execution passed |
| Init/wait helper | `sha256:469c9ea4…71eb2` | 0/0; `nc` executed as UID 1000 |
| SeaweedFS 4.54 | `sha256:4b42c212…22d15` | 0/0; authenticated persistence and restart passed |
| MLMD 1.14.0 | `sha256:51404ef4…af830` | 0/0, but **blocked**: unsupported Ubuntu 20.04 makes detection insufficient |
| Metadata writer 2.18.1 | `sha256:6f5a8d77…c20bf` | **blocked**: 47 HIGH findings in Debian/Python inventory |
| Existing MLflow/training image | `sha256:8cd171d9…3a614` | **blocked**: 60 HIGH findings; also uses SQLite/local artifacts |
| Previously qualified SeaweedFS C4.2 | `sha256:7499507f…3591a` | Security drift: now 1 HIGH (`CVE-2026-97054`, Go 1.26.10) |

The seven C16 KFP/Argo identities remain exactly as recorded in
`c16-evidence/assessment.json`; C19 verified that every local image ID still
exists. No local ID is represented as a published registry digest. The three
new clean images have SPDX evidence but no verified registry signature or SLSA
attestation, so they are locally qualified only.

## Complete minimum headless dependency graph

The six-component pipeline needs KFP API, persistence agent and
scheduled-workflow controller; Argo workflow controller and executor; KFP driver
and launcher; MySQL; MLMD server; metadata writer and Envoy; the wait/init
helper; SeaweedFS; MLflow; and the CogniFlow component image. Cache, frontend,
viewer and visualization services are not required for this pipeline because
all six components disable KFP caching and the run is headless.

The exact upstream `platform-agnostic` render produced 78 Kubernetes documents
and 21 image uses. Structural validation against the Kubernetes 1.34 OpenAPI
schema passed all 78 documents. The render is not deployable yet: several
upstream tags are mutable, it references the unqualified official MySQL image,
MLMD and metadata writer are blocked as above, the C18 UID/GID 27 patch is not
applied, and MLflow is a separate local manifest using an unqualified image.
No Kubernetes object was installed or modified.

## C10 acceptance status

| Check | Status | Evidence or blocker |
|---|---|---|
| Database migration | NOT_RUN | C18 database initialization is not authentic KFP/MLMD migration. |
| MLMD integration | BLOCKED | Exact KFP image uses unsupported Ubuntu 20.04. |
| MLflow integration | BLOCKED | Existing image has 60 HIGH findings and wrong persistence topology. |
| Artifact persistence | PASS_LOCAL | Authenticated S3 checksum and restart readback passed. |
| KFP controller readiness | NOT_RUN | Kubernetes mutation prohibited and 12 GiB gate not met. |
| Actual pipeline execution | NOT_RUN | No authorized KFP runtime; no run ID invented. |
| Candidate registration | NOT_RUN | MLflow service did not pass its image gate. |
| Candidate checksum verification | NOT_RUN | Only the storage fixture, not a model candidate, was verified. |

## Validation and resources

- Focused KFP, lineage, acceptance, database and schema tests: 43 passed, one
  upstream SQLAlchemy deprecation warning.
- Ruff passed; scoped MyPy passed for 17 source files.
- The six-component pipeline compiled; SHA-256
  `fc8622c1d5087985b843e62b95de3d96b26680d119360a00817b4113d15d49ee`.
- KFP manifest render and structural Kubernetes validation passed.
- Full regression was not repeated because C19 changed no application code.
- Gitleaks is not installed locally or in the qualified C5.8 runner image, so a
  fresh executable scan was unavailable; no runtime secrets are tracked.
- Available memory was 6.48 GiB initially and 7.27 GiB after bounded work. Root
  free space fell from 106.7 GB to about 104.1 GB due to explicitly requested
  image pulls and the Trivy Java database. Nothing was pruned.

## First Kubernetes-run prerequisites

1. Select a supported MLMD build compatible with KFP 2.18.1 and qualify it once.
2. Obtain a patched metadata-writer release or one bounded compatible rebuild;
   do not deploy the current 47-HIGH image.
3. Build one minimal MLflow runtime with MySQL metadata and SeaweedFS S3
   artifacts, then qualify its exact image and persistence/rejection behavior.
4. Patch the rendered MySQL security context to UID/GID/fsGroup 27 and replace
   all runtime images with published, signed immutable digests.
5. Verify signatures, SPDX and provenance attestations through the C11 ledger.
6. Obtain owner authorization and an isolated non-protected host with at least
   12 GiB available RAM and 60 GiB free disk, then execute negative and positive
   pipeline runs through the existing C10/C11 acceptance path.

Until those prerequisites pass, there is no real KFP run ID, MLflow candidate,
registered model version, artifact-tree digest or approval decision.
