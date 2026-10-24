# Module III handoff (design only)

Do not start Module III until PR #6 is merged. Create `feature/cogniflow-module3-ml-platform` from the resulting verified `main`, not from the current feature branch or an older local `main`.

## Stable contracts

- Prediction: `POST /predict` retains the six ordered `v1` model features, explicit inference modes, `synthetic_proxy` provenance, and fail-closed production behavior.
- Events: `SessionEvent` is the versioned Module II ingestion contract. Kafka, Bronze, Spark and Flink must continue to reject invalid versions, identifiers, timestamps and numeric bounds.
- Offline features: Delta Silver is the point-in-time source for training joins; dbt Gold is analytical output, not a training source of truth.
- Online features: Redis is a freshness-protected projection keyed by validated session ID. Its timestamp compare-and-set prevents stale overwrites; Redis is not authoritative history.
- Cross-language parity: Python, Spark and Flink use `tests/fixtures/feature_vectors.json` for names, order, units, schema version, timestamp semantics and tolerances.

## Module III integration requirements

- Kubeflow pipelines must materialize point-in-time-correct training sets from immutable Delta versions and record dataset, code, feature-schema and image digests in MLflow.
- Registry promotion must select an explicit approved MLflow version. Model artifacts and serving images require immutable digests and deployment-time signature/attestation verification.
- KServe must preserve the current request/response contract, use a least-privilege storage identity, and fail visibly when its backend or artifact is unavailable.
- Knative Eventing must consume versioned events with bounded retries, idempotency and payload-safe dead-letter metadata. It must not bypass existing schema validation.
- Online/offline skew and feature freshness need explicit SLOs, metrics and tests before training or serving automation is accepted.

## Existing controls and blockers

Production API-key authentication, request limits, secure response headers, model SHA-256 enforcement, structured telemetry, Redis stale-write protection and least-privilege CI remain mandatory. Before cloud deployment, close SEC-011 against the real cluster topology; add managed secrets, TLS, namespace RBAC, Pod Security, private/authorized control-plane access, image verification and runtime KServe/NetworkPolicy evidence. The Docker-socket Airflow profile is development-only and must not migrate into Module III.

No GCP resource, cluster, pipeline or Module III branch is created by this handoff.
