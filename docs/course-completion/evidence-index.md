# CogniFlow course-completion evidence index

**C1 audit date:** 2026-11-17 (America/Chicago)  
**C1 commit:** `20a1d1e0755f9727728fa998146f48570824e62e`  
**Policy:** Historical runtime evidence is labeled as historical. No raw Track B evidence is included.

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
| Full Python suite + coverage | `./.venv/bin/python -m pytest src/tests --cov=src --cov-report=term-missing --cov-fail-under=81`; collected 606; `test_distributed_tracing.py` failed and the following test stalled, so the process was interrupted; no coverage pass | Existing repository `.venv`; no network | NOT_PASS |
| Ruff | Repository command attempted with the existing `.venv`; result recorded before commit | Existing repository `.venv` | See commit audit |
| Gitleaks | `gitleaks` unavailable on PATH | Local host | NOT_RUN |
| Documentation checks | `markdownlint` and `lychee` unavailable; Helm and Terraform are available for relevant static checks | Local host | PARTIAL |
| Git whitespace | `git diff --check` | Repository checkout | Required before commit |
| Local synthetic demo | Not completed after the fresh suite blocker; existing focused tests cover auth, prediction, sanitized events, SQLite persistence/deduplication, anomaly, alert and recovery | Direct local components only; no Kubernetes/KServe/cloud | NOT_COMPLETED in C1 |

The historical 604-pass, 2-skipped, 5-warning, 87.08% result is recorded evidence only; it was not reproduced in C1. Local KFP and Knative records do not prove approved-model KServe serving, GKE, GCS, or a continuous full-system demonstration.
