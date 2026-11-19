# CogniFlow course-completion evidence index

**C1 audit date:** 2026-11-17 (America/Chicago)  
**Starting HEAD:** `20a1d1e0755f9727728fa998146f48570824e62e`
**Policy:** Historical runtime evidence is labeled as historical. No raw Track B evidence is included.

## C13 pre-deployment qualification — 2026-11-18

[Fresh application-image scans, first KFP controller result, real bounded
Kafka/Bronze runtime evidence and fail-closed deployment automation](c13-predeployment-qualification.md).
Kubernetes and cloud runtime remain blocked; no protected cluster was changed.

## Module I

| Requirement | Weight | Current status | Exact supporting evidence | Commit or dated runtime evidence | Verification environment | Outstanding acceptance condition |
|---|---:|---|---|---|---|---|
| FastAPI API layer | 10% | Locally/CI verified; C1 demo incomplete | `src/preprocessing_api/`, `src/tests/test_api.py`, `docs/module1/rubric-matrix.md` | Historical PR #14 baseline; audit commit `20a1d1e` | Local Python application/tests | Fresh clean-environment transcript and approved KServe path |
| KServe runtime | 10% | Implemented; approved-model serving incomplete | `src/cogniflow_kserve/`, `docs/course-rubric-2026.md` | Candidate v1 digest `3c46d07c…c20a`; no approved runtime date | No approved KServe/GKE runtime used in C1 | Explicit approval, immutable deployment, Ready, prediction and recovery |
| Training pipeline | 15% | Verified in isolated local KFP v2 runtime; historical | `docs/module3/phase4-kubeflow-training.md` | 2026-10-26; positive `cee7540f-9c9e-4078-a9d7-c61c4c4bd9fc`; negative `5143c5ae-9c98-4c4d-9f21-f5647ec63cf9` | Disposable kind KFP cluster, SeaweedFS S3, MLflow | Production/multi-user KFP and cloud artifacts |
| Knative logging | 15% | Verified in isolated local Broker/Trigger runtime; historical | `docs/module3/phase6-knative-eventing.md` | 2026-10-26; event `33fb0ed9-4b13-41f3-9da5-cdc30b444a31`; Ready, replay, restart, retry and DLQ recorded | Disposable kind cluster, Knative Eventing 1.23.0, MTChannelBasedBroker/InMemoryChannel | Persistent supported transport and authenticated production boundary; no GKE claim |
| Anomaly detection | 10% | Prior isolated runtime verified; hardened recovery regression-tested, not freshly Knative-rehearsed | `docs/module3/phase7-knative-anomaly-detection.md`, `src/tests/test_anomaly_detection.py` | 2026-10-26/27 historical runtime; 26-test hardened suite | Historical disposable kind runtime | Exact hardened image in Knative and signed production identity |

## Module II

| Requirement | Weight | Current status | Exact supporting evidence | Commit or dated runtime evidence | Verification environment | Outstanding acceptance condition |
|---|---:|---|---|---|---|---|
| MinIO object storage | 10% | Unresolved; active evidence is SeaweedFS and is not claimed as MinIO credit | `docs/module2/grading-matrix.md`, `docs/module2/testing.md` | Historical PR #19 local evidence | Isolated local Compose/SeaweedFS | Instructor equivalence or maintained MinIO runtime |
| Trino, Delta, Spark, Kafka, Flink, Airflow | 60% combined | Local runtime evidence recorded; cloud/scale deferred | `docs/module2/grading-matrix.md`, `docs/module2/testing.md` | Historical PR #19 | Isolated local Module II stack | Cloud/HA acceptance where required |
| Four cloud deployments | 20% | Not completed | `docs/module2/grading-matrix.md` | No cloud runtime evidence | No cloud environment used | Four separately accepted runtime deployments |
| Dataset strictly over 100 GB | 10% | Unresolved; benchmark intentionally not run | `docs/module2/grading-matrix.md` | No 100 GB run | Bounded local fixtures only | Process and reconcile >100,000,000,000 bytes |

## Module III / selected practical deployment

| Requirement | Weight | Current status | Exact supporting evidence | Commit or dated runtime evidence | Verification environment | Outstanding acceptance condition |
|---|---:|---|---|---|---|---|
| Authorized GKE cluster | 35% | NO-GO / cloud runtime blocked | `docs/module3/gke-gcs-readiness.md`, `docs/cloud-deployment.md` | Offline readiness only; no C1 cloud run | No GCP access used | Owner authorization, reviewed plan/apply, full runtime, cost and teardown |
| MLflow artifacts in GCS | 5% | GCS runtime blocked; local candidate integrity verified | `docs/module3/gke-gcs-readiness.md`, `docs/course-rubric-2026.md` | Historical local candidate v1; no GCS generation/digest | Local MLflow/SQLite candidate workflow | Workload Identity GCS round trip and independent digest match |
| Deployment-runner security gate | Additional gate | `BLOCKED`; exactly two HIGH findings remain | `docs/m10-3-final-runner-gate.md` | Recorded gate evidence; no new scan in C1 | Offline static/security review | Resolve both HIGH findings and rerun exact-image gate |

## C1 fresh checks and local rehearsal

| Check | Exact result | Verification environment | Status |
|---|---|---|---|
| Full Python suite + coverage | `COVERAGE_FILE=/tmp/cogniflow-c1-coverage RUFF_CACHE_DIR=/tmp/cogniflow-c1-ruff timeout 180s ./.venv/bin/python -m pytest src/tests --cov=src/preprocessing_api --cov=src/cogniflow_data --cov-fail-under=81 -o cache_dir=/tmp/cogniflow-c1-pytest-cache`; 604 passed, 2 skipped, 5 warnings; **88.87%** coverage | Existing `.venv`, authorized local loopback sockets, 2026-11-17 | PASS |
| Initial tracing failure | In sandbox, `test_httpx_injects_traceparent_and_creates_child_span` raised `PermissionError: [Errno 1] Operation not permitted` at `ThreadingHTTPServer(("127.0.0.1", 0), Handler)`; `test_fastapi_extracts_remote_parent_and_concurrent_requests_are_isolated` subsequently stalled. Both passed on the unchanged starting commit with loopback socket access. | Restricted sandbox versus authorized local test run | ENVIRONMENTAL |
| Ruff | `RUFF_CACHE_DIR=/tmp/cogniflow-ruff-cache ./.venv/bin/ruff check .`; all checks passed | Existing `.venv` | PASS |
| Gitleaks | `gitleaks` unavailable on PATH | Local host | NOT_RUN |
| Documentation and configuration | Markdown link targets checked locally; `helm lint helm/cognitive-load-monitor` passed (icon recommendation only); `terraform -chdir=infra/terraform/gke validate` could not run because Google provider 5.45.2 was not cached; `markdownlint` and `lychee` unavailable | Local host | PARTIAL; Terraform NOT_RUN |
| Git whitespace | `git diff --check` passed | Repository checkout | PASS |
| Local synthetic component rehearsal | `./.venv/bin/python -m pytest -q src/tests/test_api.py src/tests/test_activity_events.py src/tests/test_anomaly_detection.py --disable-warnings`; 103 passed, 2 warnings in 2.43s. Covers API/auth, prediction, sanitized events, SQLite persistence/deduplication, anomaly, alert and recovery | Direct local components only; no Kubernetes/KServe/cloud | PASS, component scope |

The historical 604-pass, 2-skipped, 5-warning, 87.08% result is recorded evidence only; C1 independently measured 88.87%. Local KFP and Knative records do not prove approved-model KServe serving, GKE, GCS, or a continuous full-system demonstration.

## Fresh-main qualification — 2026-11-17

See [fresh-main-qualification.md](fresh-main-qualification.md) for the locked-install
baseline at `809d3a860e305533de77c7296fa510bca8c71da6` and the tested local changes:
606 passed, 2 skipped, 5 warnings, **87.13% across all nine coverage packages**
(81% gate); Ruff, scoped MyPy, KFP compilation and Helm lint/render passed.
This coverage scope differs from C1’s API/data-only 88.87%. The adapter now clears
readiness on failed reload. A new component rehearsal verifies actual API events
through durable consumer/anomaly/alert stores with replay and outage recovery.
Module II’s 72 selected compatibility tests passed; infrastructure was not rerun.
Historical 0.90 model accuracy remains documented, not reproduced, because exact
inputs/artifacts and the configured DVC remote are missing. No approval, cluster,
cloud execution, benchmark or push occurred; M10.3 remains NO-GO.

## Synthetic candidate qualification — 2026-11-17

[Owner-review record](model-candidate-qualification.md) and
[exact candidate packet](synthetic-candidate-20261117.json): new local
`cogniflow-fresh-synthetic-20261117/1`, 210 synthetic rows, 126/42/42 split,
registered tree `4119d9aa3cbe3ba63d69b434c11b0209eba8b1ff331603b5cb5459d23b423f60`.
Independent input regeneration, refitting and registered-skops inference checks pass.
Forest/logistic validation accuracy and macro-F1 are 1.0; majority 1/3 and 1/6.
All validation/test feature vectors also occur in training, so this is engineering
evidence only. The historical locked metrics report was recovered from Git; historical
dataset/model reproduction remains **NOT_REPRODUCED**. The candidate is unapproved,
production packaging rejects it, and KServe Kubernetes runtime remains NOT_RUN.
The serving validator now accepts the existing sanitized release-package contract.
Full regression: 606 passed, 2 skipped, 87.13% coverage; M10.3 remains NO-GO.

## C2.2 independent evaluation — 2026-11-17

[Review record](c22-independent-evaluation.md), [predeclared protocol](c22-evaluation-protocol.md),
and [candidate packet](c22-candidate.json). Implementation/training commit
`9bc1e97d49bfbda8289a59fa7614867db33e1d17`; old candidate files unchanged.
New `cogniflow-c22-independent-20261117/1` uses 125/43/42 rows and 36/12/12 disjoint
feature groups. Logistic regression wins the exact 1.0 validation tie against the
forest by simplicity; final test accuracy/macro-F1 1.0/1.0, synthetic-only.
Full tests: 623 passed, 2 skipped, 87.20% coverage. KFP compilation/negative lineage
checks pass; real KFP runtime, approval and KServe deployment remain NOT_RUN.
M10.3 NO-GO and SEC-022 remain unchanged.

## C5.1 FastAPI/KServe repair — 2026-11-17

[Read-only diagnosis and authorized-runtime procedure](c51-fastapi-kserve-repair.md).
The qualification cluster has a Ready predictor revision but a failed route because
KServe references the nonexistent `kubeflow/kubeflow-gateway`; FastAPI correctly
stays unready while it cannot verify model provenance. The Helm chart now emits both
required cluster-local visibility labels and explicit KServe predictor scale fields.
A fail-closed offline validator rejects missing or unexpected gateway references.
Local verification: 630 passed, 2 skipped, 87.20% coverage; Ruff, scoped MyPy,
Helm lint and Knative rendering passed. No cluster object, model approval, Eventing
setting, or historical evidence changed.

## C5.3 FastAPI/KServe image remediation — 2026-11-17

[Security and runtime record](../security-audit/c53-fastapi-kserve-remediation.md).
Digest-pinned Wolfi/Python 3.13 builds replaced the vulnerable local FastAPI and
KServe images. Exact replacement IDs independently scanned at 0 HIGH / 0 CRITICAL,
generated SPDX SBOMs and retained BuildKit provenance metadata. Isolated direct and
API-to-KServe inference, authentication, outage/restart recovery and wrong-model
rejection passed with the disposable qualification fixture. Full regression: 630
passed, 2 skipped, 87.20% coverage. Images are not published or signed; kubectl and
gateway runtime blockers remain. M10.3 NO-GO and SEC-022 are unchanged.

## C5.4 security-qualified kubectl — 2026-11-17

[Qualification record](../security-audit/c54-kubectl-qualification.md). The
official 1.35.10 client still has three HIGH Go-module findings, so an authentic
v1.35.10 source archive was rebuilt with Go 1.27.4, `x/net` 0.62.0 and the
required fixed dependency closure. Two builds were byte-identical at SHA-256
`130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef`.
Trivy 0.76.2 reported 0 HIGH / 0 CRITICAL and generated an 84-package SPDX SBOM.
Help, invalid arguments, kubeconfig isolation and read-only v1.34.11 cluster
queries passed. No cluster object changed. The standalone client passes, but
M10.3 remains NO-GO until the exact runner is rebuilt and independently passes
its whole-image gate; gateway and registry prerequisites also remain open.

## C5.5 deployment-runner integration — 2026-11-17

[Whole-image record](../security-audit/c55-runner-integration.md). The qualified
kubectl was reconstructed, integrated and extracted from the exact runner with
the expected SHA-256. The new local image ID is
`sha256:073432d2da9a1c4ceb18ca7d3654984fbed88635d207ab59407b65c01f70d8a7`.
BuildKit provenance/SBOM generation passed and the independent SPDX inventory
contains 1,463 packages. The current whole-image scan is **NO-GO: 5 HIGH,
0 CRITICAL**, all outside kubectl: three Ubuntu packages, Actions Runner
WebUtilities and Cosign `x/net`. Phase-5 runner and cluster tests were correctly
not run after the mandatory image gate failed. No container was started, no
cluster or cloud object changed, and nothing was published or pushed.

## C5.6 final runner remediation — 2026-11-17

[Remediation record](../security-audit/c56-runner-remediation.md). Authenticated
Ubuntu fixes and a source-built Cosign `v3.1.4-cogniflow.1` candidate passed
their standalone integrity and zero-HIGH/zero-CRITICAL checks. The latest
official Actions Runner is still vulnerable 2.338.2. A bounded source candidate
contained fixed WebUtilities 8.0.34, but its upstream suite finished 1,161
passed / 3 failed and therefore did not qualify. The complete runner was not
rebuilt or started; no final C5.6 image, SBOM, provenance, runtime or cluster
claim exists. Decision: **BLOCKED**; M10.3 remains NO-GO.

## C5.7 Actions Runner qualification — 2026-11-17

[Independent package record](../security-audit/c57-actions-runner-qualification.md).
No fixed official release exists, so signed upstream commit
`a9dcf1bf7a78751648ff630fd4d0152471293487` was built with WebUtilities
8.0.34, .NET 8.0.428/8.0.34 and Node 24.22.3. The deterministic npm-stripped
archive SHA-256 is
`6d552c6b6acf854247f0b4c439586dd53196f54b94ba8320c76696d6a18d2e46`.
The complete suite passed 1,165/1,165 after a documented test-only fix for an
upstream `/proc` startup race; no production source was changed. Trivy 0.76.2
reported 0 HIGH / 0 CRITICAL and an independent 383-package SPDX SBOM was
generated. Decision: **PASS for the independent Actions Runner package**. The
complete M10.3 image has not been rebuilt or qualified, so M10.3 remains NO-GO.

## C5.8 final M10.3 runner qualification — 2026-11-17

[Whole-image and runtime record](../security-audit/c58-final-runner-qualification.md).
The nine-input offline build integrated the qualified Actions Runner, kubectl,
Cosign and authenticated Ubuntu fixes. Exact local image
`sha256:fea8be5e98ba4defff5f8d23059c9d31103f7014b4e33b42c1aa1dcb0498d44a`
passed complete Trivy OS/.NET/Go/Python analysis at 0 HIGH / 0 CRITICAL and
produced BuildKit provenance/SBOM plus an independent 1,463-package SPDX SBOM.
The unregistered network-disabled runtime checks passed, including tool hashes,
controlled Cosign verification, Helm render and Node/hashFiles. Full regression:
631 passed, 5 skipped, 87.20% coverage. **Local M10.3: PASS.** Registry
publication, signing/attestation, owner approval and Kubernetes execution remain
separate NO-GO gates.

## C5.9 immutable release preparation — 2026-11-17

[Release packet and owner procedure](c59-immutable-release-preparation.md).
The three expected local OCI index IDs still exist. C5.8 raw Trivy, SPDX and
BuildKit metadata match their recorded checksums, and the runner runtime
manifest remains independently identified. The C5.3 FastAPI/KServe raw
scan/SBOM/provenance files are no longer retained locally, so the machine-readable
release ledger fails closed as **BLOCKED**. Proposed Artifact Registry paths,
keyless signing/attestation checks, exact gateway correction, rollback, and the
legacy-model-only infrastructure test are prepared but were not executed. No
registry, cloud, Kubernetes, runner, or model state changed; M10.3 deployment
NO-GO and SEC-022 remain unchanged.

## C6 real KFP execution preflight — 2026-11-17

[Measured runtime and candidate evidence](c6-kfp-runtime-preflight.md). Neither
retained kind cluster contains KFP, and no authorized endpoint exists. Host RAM,
swap, and `/tmp` headroom fail the existing local-start gate. The retained
historical component image has no registry, is bound to the wrong code revision,
and lacks a current complete zero-HIGH/zero-CRITICAL qualification. No workload
was submitted and no KFP run ID was created. The C2.2 local candidate was
independently reverified with exact dataset, split, model and artifact digests,
but remains non-KFP, unapproved, and undeployed. Full validation passed 632 tests
with 2 skips and 87.20% coverage; Ruff and scoped MyPy passed. Decision:
**BLOCKED** pending an owner-authorized isolated runtime and qualified component
image. C5.9, M10.3 deployment NO-GO, and SEC-022 are unchanged.

## C7 Knative Eventing and anomaly qualification — 2026-11-18

[Security and isolated runtime record](c7-knative-anomaly-qualification.md).
Fresh consumer and anomaly/sink OCI images built from committed revision
`1eb7ff1` passed complete Trivy scans at 0 HIGH / 0 CRITICAL and include SBOM
and BuildKit provenance evidence. A bounded real-application container run
verified sanitized persistence, deduplication, normal/no-alert behavior, two
deterministic alerts, transactional-outbox recovery without new traffic,
restart persistence and retryable failure. Full validation passed 632 tests
with 5 skips and 87.20% coverage; Ruff, scoped MyPy, manifest parsing and the
immutable production renderer passed. Decision: **PASS_LOCAL** only. The fresh
run did not execute Knative controllers, Broker/Trigger delivery or a DLQ;
historical October runtime evidence remains distinct. Publication/signing,
durable authenticated transport and an owner-authorized isolated Knative run
remain blockers. C6 stays BLOCKED.

## C8.1 MinIO and large-data readiness — 2026-11-18

[Exact-image and bounded generator record](../module2/c81-minio-large-data-readiness.md).
The official AIStor Free amd64 manifest was resolved without execution and
failed the normal gate with 22 HIGH findings, root-default configuration and an
unprovided mandatory license. The retained community image failed with 68 HIGH,
6 CRITICAL and an end-of-life base. MinIO decision: **NO-GO**; SeaweedFS remains
separate evidence. A 256,000,000-byte generator probe and full resume scan
reconciled exact bytes and identities, but no pipeline processing occurred.
Measured laptop memory, `/tmp` and disk capacity are insufficient for the full
workload. The >100 GB and four cloud criteria remain incomplete; SEC-022, C6,
C7 and M10.3 statuses are unchanged.

## C8.2 bulk ingestion and reconciliation — 2026-11-18

[Executable implementation and validation](../module2/c82-bulk-ingestion.md).
New production code incrementally verifies generated partitions, publishes
bounded Kafka batches, persists acknowledged offsets and checksum-read-back
Bronze objects, resumes from atomic checkpoints, captures distributed Spark
input/Delta accounting and fails final reconciliation without actual Gold
evidence. Failure, corruption, duplicate and restart paths are regression-tested.
The broader Module II suite passed 87 tests; Ruff and scoped MyPy passed. Fresh
runtime preflight failed the unchanged 6 GiB memory gate, so Kafka/SeaweedFS and
Spark execution are `NOT_RUN`. Full regression passed 642 tests with 5 skips and
86.99% coverage. This advances implementation readiness only; the MinIO, cloud
and >100 GB runtime rubric items remain incomplete.

## C14 KFP API Server security remediation — 2026-11-18

[Targeted security and compatibility record](c14-kfp-api-security-remediation.md).
The C13 report was classified finding by finding: 68 OS and 27 embedded Go
findings, with no Python, JavaScript or unsupported-runtime findings. Official
KFP 2.18.1 still had 48 HIGH OS findings. One bounded build from the verified
2.18.1 source commit produced non-root local image
`sha256:d70accf415ef407fd23fd7a790cfd8f9ec9877324018434264fdb66d378859ad`
with a complete unsuppressed 0 HIGH / 0 CRITICAL scan. Existing CogniFlow tests
and focused upstream authorization tests passed; MySQL initialization and
fail-closed missing-Kubernetes behavior were verified. Decision: **BLOCKED**
because task restrictions prohibit the isolated Kubernetes API needed for
readiness, live SDK, SeaweedFS and authentication checks. The production KFP
matrix, retained clusters, C6 and SEC-022 are unchanged.

## C16.1 KFP database qualification — 2026-11-19

[Database selection and bounded remediation record](c16-1-database-qualification.md).
The exact KFP 2.18.1 production overlay selects MySQL for `mlpipeline`,
`cachedb`, and MLMD's `metadb`; PostgreSQL is not the supported production
choice. The pinned MySQL 8.4.13 image failed a complete unsuppressed scan with
42 HIGH and 2 CRITICAL findings across Oracle Linux, embedded MySQL Shell
Python packages, and gosu. The one allowed remediation stopped before image
creation because its verified Go 1.27.4 builder was Debian-based while the
recipe invoked `apk`; it was not retried. Decision: **BLOCKED**. No database
container, Kubernetes object, cloud resource, registry, or model was changed.

## C16.2 MySQL security remediation — 2026-11-19

[Bounded build record](c16-2-mysql-security-remediation.md). The Debian/Alpine
builder mismatch was corrected, gosu 1.20 built successfully from its verified
revision with Go 1.27.4, and the four vulnerable Oracle Linux packages upgraded
to their scanner-fixed release. The sole candidate build then stopped before
image creation because `pyOpenSSL 26.0.0` requires `cryptography <47` while the
security fix requires `cryptography 50.0.0`. A resolver-only check established
that `pyOpenSSL 26.4.0` is compatible, but no second build was attempted.
Decision: **BLOCKED**. No scan or database runtime claim was fabricated.

## C16.3 final MySQL dependency correction — 2026-11-19

[Build and security record](c16-3-mysql-dependency-correction.md). The sole
bounded candidate built and its raw complete Trivy scan reported 0 HIGH and
0 CRITICAL. Qualification was nevertheless rejected: MySQL Shell's OCI package
conflicted with the requested cryptography/pyOpenSSL fixes, and pip left
duplicate package metadata directories with the old `METADATA` files missing.
This made the scanner inventory incomplete and accepting it would hide packages.
Decision: **NO-GO**. Functional database tests were correctly not started.

## C17 minimal MySQL runtime qualification — 2026-11-19

[Contract and bounded build record](c17-minimal-mysql-runtime.md). Exact KFP
2.18.1 source confirms MySQL Shell/OCI/Python are unnecessary: KFP and MLMD use
the MySQL protocol, while the official entrypoint needs only server-minimal
binaries and gosu. The sole build removed exactly the optional `mysql-shell`
RPM, but a fail-closed inventory assertion found an unowned residual
`/usr/lib/mysqlsh` tree, so no image was exported or scanned. Decision:
**BLOCKED**. Future work requires a from-minimal-RPM packaging path, not another
derived-image cleanup loop.

## C18 end-to-end platform completion — 2026-11-19

[Implementation and execution record](c18-platform-completion.md). C18 replaced
the failed derived-image experiments with a minimal Oracle Linux plus official
MySQL 8.4 server-minimal package. Exact local image
`sha256:367c695a6870d1fed993457575846f13071ea3c8cee88d54a311251ff4dbf0f3`
scanned at 0 HIGH / 0 CRITICAL and passed real initialization, authentication,
schema, persistence, restart and integrity checks as non-root. The
[machine-readable assessment](c18-evidence/assessment.json) binds the local
identity and evidence checksums. KFP execution remains blocked on publication,
signing, the remaining runtime-role ledger, isolated-host resources and owner
authorization; no run ID, model approval, protected-cluster mutation or cloud
claim was created.
