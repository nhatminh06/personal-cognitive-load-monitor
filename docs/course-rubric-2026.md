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
| Training pipelines using Kubeflow Pipelines, Hera or similar | Actual multi-component pipeline run for preparation, training, evaluation and registration | 15% | Kubeflow Pipelines v2 standalone | Six separate KFP tasks validate, prepare, train, evaluate/select, register a candidate and record provenance through explicit object-store artifacts | **Verified in isolated local runtime** | Production/multi-user KFP and cloud artifact storage remain outside this local proof | `pipelines/cogniflow_training_pipeline.py`; `src/cogniflow_data/kfp_tasks.py`; `docs/module3/phase4-kubeflow-training.md` | Execute pinned 180-row run; verify digests, 108/36/36 splits and candidate registration; corrupt checksum must prevent training | Run `cee7540f-9c9e-4078-a9d7-c61c4c4bd9fc`, negative run `5143c5ae-9c98-4c4d-9f21-f5647ec63cf9`, compiled YAML, artifacts and MLflow version 1 | PR #13 | Local criterion met; production hardening and GCS remain PR #17 scope |
| Knative Eventing for capturing logs | Privacy-safe inference activity emitted as CloudEvents through a real Broker/Trigger to a consumer | 15% | Knative Eventing 1.23 MTChannelBasedBroker + InMemoryChannel | Versioned sanitized producer, Broker/Trigger, SQLite consumer/DLQ, dedupe, metrics and finite retries | **Verified in isolated local runtime** | Replace development-only in-memory transport and unauthenticated internal sink boundary before production | `src/preprocessing_api/activity_events.py`; `src/cogniflow_eventing/`; `deploy/knative/`; `docs/module3/phase6-knative-eventing.md` | One real API request produces one correlated sanitized event; replay, restart, retry/recovery and exhausted-retry DLQ pass | Broker/Trigger Ready, event/correlation IDs, SQLite counts, consumer metrics and DLQ event match | PR #15 | Local criterion met in `demo_rule`; KServe remains independently blocked |
| Real-time anomaly detection based on Knative Eventing | Subscriber evaluates objective API/serving anomalies in bounded windows and emits deduplicated alerts | 10% | Deterministic thresholds over persistent event-time windows | SQLite-backed detector, transactional outbox, alert sink, dedupe/cooldown, metrics and dashboard | **Verified in isolated local runtime** | Production repository digest/signature, persistent Broker transport and authenticated service boundary | `src/cogniflow_anomaly/`; `deploy/knative/anomaly*.yaml`; `docs/module3/phase7-knative-anomaly-detection.md` | Normal fixture produces no alert; injected error/latency/rate anomaly produces one alert within the SLO | Exact event/alert IDs, metrics/dashboard queries, 3.558 ms final-image latency, restart/outbox recovery | PR #16 | Local criterion met; cloud hardening remains PR #17 |
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

- The current PR #16 regression baseline (2026-10-26) is 209 tests at 88.21% combined coverage, with Ruff and scoped MyPy passing.
- Module I runtime evidence is dated 2026-10-23 in [`module1/verification.md`](module1/verification.md).
- Module II runtime evidence is dated 2026-10-24 through 2026-10-25 in [`module2/testing.md`](module2/testing.md).
- Module III Phase 3 local hardening evidence is dated 2026-10-26 in [`module3/phase3-model-serving.md`](module3/phase3-model-serving.md).
- Module III KFP evidence is dated 2026-10-26 in [`module3/phase4-kubeflow-training.md`](module3/phase4-kubeflow-training.md).
- Module III Knative Eventing evidence is dated 2026-10-26 in [`module3/phase6-knative-eventing.md`](module3/phase6-knative-eventing.md).
- Module III anomaly-detection evidence is dated 2026-10-26/27 in [`module3/phase7-knative-anomaly-detection.md`](module3/phase7-knative-anomaly-detection.md).
- Historical evidence retains its original scope. The local KFP and Eventing runs do not prove KServe, anomaly detection, GKE, GCS or video completion.
