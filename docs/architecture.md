# Implemented architecture

**Current implementation snapshot: 2026-10-26.** This page describes what exists now. The unimplemented grading target is explicitly separated in [`module3/final-rubric-architecture.md`](module3/final-rubric-architecture.md).

```mermaid
flowchart TB
    Client --> API[FastAPI]
    API --> Rule[demo_rule]
    API --> Local[verified local skops model]
    API --> KClient[KServe HTTP client]
    Events[Session events] --> Kafka
    Kafka --> Bronze[SeaweedFS S3 Bronze]
    Bronze --> Spark[Spark / Delta Silver]
    Spark --> Trino --> DBT[dbt Gold]
    Kafka --> Flink --> Redis
    Redis --> API
    DVC --> Train[local training]
    Train --> MLflow[local MLflow registry]
    Prom[Prometheus] --> Grafana
    API --> Loki
    API --> Tempo
```

## Runtime-verified locally

- FastAPI request validation, authentication, explicit `demo_rule`, `local_model` and `kserve` modes, readiness and no silent fallback.
- Deterministic/DVC training, candidate-only MLflow registration, explicit approval command and exact artifact-tree SHA-256 checks.
- Kafka ingestion, Bronze object persistence, Spark/Delta Silver, Trino/dbt Gold, Airflow fixed-command orchestration, Flink event-time aggregation and Redis freshness protection.
- Prometheus/Grafana metrics, Loki structured logs and Tempo traces in dated Module I/II verification runs.
- Terraform-managed local kind cluster and Helm demo-rule release on loopback port `18000`.

## Implemented but not runtime-verified

- Approval-bound Phase 3 model packaging and isolated local-model Helm release. The current MLflow version 2 remains a candidate, so no image or deployment exists.
- KServe 0.20 custom `.skops` ModelServer, strict client behavior and Standard-mode
  `InferenceService` manifests. The controller and a non-model contract responder
  were runtime-verified in a disposable cluster; approved-model Kubernetes
  inference remains blocked pending explicit approval and a retrievable artifact.
- GKE Terraform, Workload Identity definitions, GCS bucket and cloud deployment workflow. They are statically validated only.

## Not implemented

- Kubeflow Pipelines training orchestration.
- An approved model package and immutable image deployed through the implemented
  custom KServe runtime.
- Knative Eventing logging Broker/Trigger/consumer.
- Knative-based real-time anomaly detector.
- Authorized GKE/GCS runtime and full demonstration video.

## Stable serving contract

`INFERENCE_MODE` accepts only `demo_rule`, `local_model` or `kserve`. Explicit modes use only the selected backend; absence, timeout, invalid output or provenance failure returns a visible failure and keeps readiness closed. The six ordered feature names and `PredictionResponse` remain stable. `/model-info` reports verified manifest-backed provenance in local-model and KServe modes; KServe readiness performs a live metadata check.

The stock KServe sklearn server does not document `.skops` support, so the implemented target uses a digest-pinned custom KServe Python runtime that reuses the existing manifest/trusted-type checks. See the [KServe runbook](module3/phase5-kserve-inference.md).

## Deployment ownership and restrictions

- Terraform owns the existing local demo release; experimental Helm releases use separate namespaces and names.
- PersonalOS remains on host port `8000`; CogniFlow demo access is `18000`; experimental serving reserves `18001`.
- Cloud deployment must pin OCI repository digests and enforce image signatures/attestations.
- SEC-022 Spark is accepted only for isolated local development with trusted synthetic data and is prohibited in Kubernetes/GKE.
- No current evidence claims KServe scale-to-zero, cloud HPA behavior, production ingress, GCS-backed artifacts or cloud security controls.
