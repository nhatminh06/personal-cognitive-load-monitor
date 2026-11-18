# CogniFlow course-completion evidence index

**C1 audit date:** 2026-11-17 (America/Chicago)  
**Starting HEAD:** `20a1d1e0755f9727728fa998146f48570824e62e`
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
