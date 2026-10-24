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

No commit, push, PR, merge, history rewrite, cloud provisioning or remote deployment occurred.
