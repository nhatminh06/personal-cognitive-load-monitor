# Remediation log

- Added shared production authentication, body limits and browser security headers in `src/preprocessing_api/security.py`; applied it to sensitive API routes.
- Added production SHA-256 verification before joblib deserialization and removed internal exception/path details from model logs.
- Replaced raw DLQ payloads with SHA-256 and byte length. Flink now validates versions, UUIDs, session IDs and numeric ranges before event-time processing.
- Restricted all local published ports to loopback and enabled Redis authentication end to end.
- Removed model-registry build arguments/downloads from Docker builds; CI packages an explicitly retrieved model before build.
- Reduced GitHub token permissions to per-job scope, validated dispatch inputs, removed the mutable image tag, and limited deployment/OIDC to `main`.
- Added production `APP_ENV` and external Secret support to Helm.
- Updated vulnerable locked dependencies and pinned Ruff to the verified policy version.
- Added API, model-integrity and DLQ privacy regression tests.
- Expanded the enforced coverage denominator to both application packages.
- Disabled persisted checkout credentials and publishing-job dependency caching; removed direct workflow-expression interpolation from deploy shell.
- Added explicit non-root users to Airflow, dbt, Flink, Spark runner and SeaweedFS images.
- Removed curl and unused packaging tools from runtime images, upgraded Flink's shaded Jackson dependencies, and required GKE control-plane CIDRs plus protected workload metadata.
- Migrated Airflow to 3.3.2 and removed Docker-socket/root execution in favor of authenticated fixed-command runners.
- Replaced archived MinIO with pinned SeaweedFS 4.50 after hash-verifying 91 copied objects while preserving the original volume.
- Upgraded dbt-core/dbt-trino normally so sqlparse 0.6.0 resolves, then passed two full builds and explicit tests.
- Configured and read back GitHub branch and production-environment protections without merging or deploying.
- Recorded Spark image vulnerability SEC-022 as a release blocker instead of treating isolation as remediation.
- Rejected official Spark 3.5.9 and 4.1.3 candidates after complete scans showed hundreds of fixable High/Critical findings.
- Removed caller-selected publication tags, captured the pushed registry digest, and rendered Helm deployment by immutable digest.
- Split SeaweedFS into an internal raw backend and a stateless S3 gateway so application workloads cannot reach master/filer/volume APIs.

During the security-audit task itself, no commit, push, PR, merge, history rewrite, cloud provisioning or remote deployment occurred. A later, separately authorized publication task committed these remediations, merged the updated `main` into the feature branch without rewriting history, pushed normally, and opened draft PR #6. No PR merge, cloud provisioning or remote deployment was performed by that task.
