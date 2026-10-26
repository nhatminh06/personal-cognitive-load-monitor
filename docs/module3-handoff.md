# Module III handoff

**Updated 2026-10-26 after PR #11 merged.** Phases 1–3 established historical feature contracts, reproducible candidate training/registration and approval-bound local serving machinery. They did not implement or run Kubeflow, a KServe `InferenceService`, Knative Eventing, a Knative anomaly detector, GKE/GCS integration or the final video.

The authoritative next-step documents are:

- [weighted course rubric](course-rubric-2026.md);
- [final rubric architecture](module3/final-rubric-architecture.md);
- [implementation roadmap](module3/implementation-roadmap.md);
- [resource and cost plan](module3/resource-and-cost-plan.md);
- [full demonstration contract](demo/full-rubric-demo.md).

## Stable contracts

- `POST /predict` preserves the existing request/response schema, six ordered `1.0` model features, explicit inference source, synthetic-proxy provenance and fail-closed explicit modes.
- `SessionEvent` remains the Module II ingestion contract. Kafka, Bronze, Spark and Flink reject invalid versions, identifiers, timestamps and bounds.
- Delta Silver is the point-in-time historical source; dbt Gold is analytical output, not training truth.
- Redis is a freshness-protected online projection, not authoritative history.
- `tests/fixtures/feature_vectors.json` defines cross-language names, order, units, timestamps and tolerances.
- Model deployment names an exact approved MLflow version and registered artifact-tree SHA-256. Packaged model provenance and OCI repository digest are independently verified.

## Next milestone

PR #13 implements Kubeflow Pipelines v2 around the existing preparation/training logic. Acceptance requires a real run with pinned inputs and component images, chronological evaluation, immutable lineage and candidate-only MLflow registration. Compiled YAML or local sequential scripts alone do not pass.

Subsequent milestones add the custom `.skops` KServe runtime, Knative logging, deterministic anomaly detection, authorized GKE/GCS integration and final evidence/video in that order.

## Preserved security boundaries

Strict schema validation, API authentication, bounded HTTP, read-only Trino access, candidate/approved separation, pre-deserialization artifact verification, non-root/read-only workloads, immutable images, no silent fallback and secret-free telemetry remain mandatory. Image signing/attestation must be enforced before cloud deployment.

SEC-022 is accepted risk for isolated local development only through 2027-01-23. Its Spark runtime is prohibited in production, staging, Kubernetes and GKE. The development-only Airflow execution boundary also must not migrate to cloud deployment.
