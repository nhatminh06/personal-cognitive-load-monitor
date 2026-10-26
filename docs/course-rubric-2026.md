# CogniFlow course rubric — 2026

**Authoritative grading map. Last audited: 2026-10-26.** This document maps the owner's two-page assignment to repository evidence. It does not replace the separate [27-item engineering checklist](requirement-matrix.md). A manifest or design alone is not runtime proof.

## Status vocabulary

- **Verified in local runtime:** executed locally and the output was inspected.
- **Verified in GitHub CI:** passed in an observed GitHub Actions run.
- **Statically validated:** parsed, linted or rendered, but not exercised at runtime.
- **Implemented, not runtime-tested:** executable code/configuration exists without current runtime proof.
- **Not implemented:** required executable behavior does not exist yet.
- **Blocked:** permissions, resources, approval or cost currently prevent verification.

## Weighted rubric

| Instructor requirement | Technical interpretation | Weight | Selected technology | Existing CogniFlow implementation | Verification level | Missing functionality | Location | Required acceptance test | Expected evidence | Target milestone | Dependencies / blockers |
|---|---|---:|---|---|---|---|---|---|---|---|---|
| API layer | Stable authenticated preprocessing and prediction API with observable, fail-closed backend selection | 10% | FastAPI + Pydantic | `/predict`, `/health`, `/ready`, `/model-info`, metrics, API-key auth, six-feature contract and explicit inference source | **Verified locally and in CI** | Final KServe end-to-end request evidence | `src/preprocessing_api/`; `src/tests/test_api.py`; `src/tests/test_model_client.py` | Submit valid/invalid/auth/backend-failure requests; prove response schema and no fallback | Test report, API transcript, metrics and trace IDs | PR #14 | Approved synthetic-demo model for live KServe path |
| KServe, ModelMesh Serving or KubeRay | A real Kubernetes model-serving runtime, not only YAML | 10% | KServe `InferenceService` with a custom CogniFlow Python runtime | KServe client path and manifests exist; local approved-model packaging and provenance gates exist | **Statically validated; runtime not verified** | Custom KServe server for `.skops`; install KServe; deploy exact approved model; readiness, failure and recovery tests | `kserve/inferenceservice.yaml`; `helm/cognitive-load-monitor/templates/inferenceservice.yaml`; `scripts/package_approved_model.py` | `InferenceService` reaches Ready; FastAPI returns contract-compatible predictions; corrupt/missing artifact fails closed | `kubectl` status/events, immutable image/model digests, request transcripts | PR #14 | PR #13; explicit model approval; sufficient cluster resources |
| Training pipelines using Kubeflow Pipelines, Hera or similar | Actual multi-component pipeline run for preparation, training, evaluation and registration | 15% | Kubeflow Pipelines v2 standalone | Deterministic preparation, chronological training/evaluation and MLflow candidate registration exist as scripts/DVC stages | **Core logic verified locally; Kubeflow pipeline not implemented** | KFP components, compiler, immutable component images, submitted run and failure tests | `src/cogniflow_data/training.py`; `scripts/prepare_training_dataset.py`; `scripts/train_historical_model.py`; `dvc.yaml` | Execute pinned preparation → train → evaluate → register run; verify manifests/digests and candidate-only registration | Compiled pipeline, run ID/UI capture, component logs, MLflow lineage | PR #13 | Standalone KFP or authorized GKE; object-store pipeline root |
| Knative Eventing for capturing logs | Privacy-safe inference activity emitted as CloudEvents through a real Broker/Trigger to a consumer | 15% | Knative Eventing Broker + Trigger + logging consumer | Structured application logs and Loki exist, but they are not Knative Eventing | **Not implemented** | Stable CloudEvent producer/consumer, Broker/Trigger, retries, dedupe, dead-letter sink and failure visibility | Planned under `src/` and `deploy/knative/`; architecture in `docs/module3/final-rubric-architecture.md` | One API request produces one sanitized event at the consumer; retry/DLQ/dedup tests pass | Event IDs/correlation IDs, Broker/Trigger Ready status, consumer/DLQ logs | PR #15 | KServe path and Knative Eventing installation |
| Real-time anomaly detection based on Knative Eventing | Subscriber evaluates objective API/serving anomalies in bounded windows and emits deduplicated alerts | 10% | Deterministic thresholds, with EWMA only if justified by fixtures | Prometheus metrics and Flink cognitive features do not satisfy this requirement | **Not implemented** | Detector service, versioned rule config, window state, alert schema, dedupe and latency metric | Planned under `src/` and `deploy/knative/` | Normal fixture produces no alert; injected error/latency/rate/staleness anomaly produces one alert within the SLO | Input events, detector metrics, alert event, measured latency, dashboard capture | PR #16 | PR #15 event flow; deterministic fixtures |
| One GKE cluster, or GKE plus GCE, deploying the components | Deploy the grading-relevant platform on an authorized GKE environment. GCE is not scored separately | 35% | GKE Standard, selected alternative | Terraform defines a regional GKE cluster, IAM, GCS and Artifact Registry | **Statically validated; cloud runtime blocked** | Right-size topology; install KFP/KServe/Knative; TLS/ingress/IAM; full runtime and teardown evidence | `infra/terraform/gke/`; `.github/workflows/ci-cd.yaml` | Authorized apply, workload readiness, end-to-end demo, controlled failure/recovery and teardown | Terraform plan/apply logs, workload inventory, endpoint transcript, billing export | PR #17 | Explicit owner approval, GCP project/budget/credentials; cost; production security gates |
| Model registry backed by cloud object storage | MLflow metadata binds exact model versions to artifacts stored in GCS | 5% | MLflow Registry + private versioned GCS bucket | Local MLflow registry and artifact-tree integrity are verified; Terraform defines a model bucket | **Local registry verified; GCS integration blocked** | GCS artifact root, Workload Identity, retention/versioning, actual upload/download and digest proof | `scripts/train_historical_model.py`; `scripts/approve_model_candidate.py`; `infra/terraform/gke/main.tf` | Register candidate whose source is GCS; independently retrieve exact version and match the artifact-tree SHA-256 | MLflow version/run, `gs://` URI, object generation, digest transcript and IAM audit | PR #17 | Authorized GCP resources; least-privilege identity; explicit model approval only for deployment |

**Scoring total:** technical `10 + 10 + 15 + 15 + 10 = 60%`; practical `35 + 5 = 40%`; overall `100%`. The unselected GCE-only 20% alternative is not added to the GKE score.

## Deliverables

| Deliverable | Current state | Acceptance condition | Target |
|---|---|---|---|
| GitHub source with detailed installation and execution instructions | Repository and substantial README exist; final cloud commands are not runtime verified | A fresh authorized environment follows pinned instructions through the full flow | PR #18 |
| Real demonstration video | **Not recorded** | Unedited-enough recording shows the complete working flow, failure behavior, evidence and teardown described in [`demo/full-rubric-demo.md`](demo/full-rubric-demo.md) | PR #18 |

## Additional engineering targets — not separate rubric points

HPA, Prometheus/Grafana/Loki/Tempo, DVC, Delta/Trino, Kafka/Flink/Redis, model attestations, a 100 GB benchmark and KServe scale-to-zero improve engineering quality but are not separately weighted in the provided rubric. Scale-to-zero requires observed zero replicas, cold activation and successful inference; an annotation alone is not evidence. The example architectures and example datasets are guidance, not extra scoring categories.

The cognitive-load use case remains valid, but all current labels are synthetic proxies. No result may be described as medical or psychological validation.

## Evidence freshness

- The current regression baseline (2026-10-26) is 152 tests at 89.41% combined coverage, with Ruff and MyPy passing.
- Module I runtime evidence is dated 2026-10-23 in [`module1/verification.md`](module1/verification.md).
- Module II runtime evidence is dated 2026-10-24 through 2026-10-25 in [`module2/testing.md`](module2/testing.md).
- Module III Phase 3 local hardening evidence is dated 2026-10-26 in [`module3/phase3-model-serving.md`](module3/phase3-model-serving.md).
- Historical evidence retains its original scope. It does not prove Kubeflow, KServe, Knative, GKE, GCS or video completion.
