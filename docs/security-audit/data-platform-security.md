# Data platform security

Kafka is plaintext and unauthenticated only inside the isolated local Compose network; its host listener is loopback-only. Producers require all acknowledgements and idempotence. Consumers validate independently, commit only after handling or durable quarantine, and never copy raw invalid payloads into the DLQ. End-to-end exactly-once is not claimed.

Bronze keys are derived from validated schema date and event UUID digests, not user path fragments. Writes carry SHA-256 metadata and offsets follow durable handling. SeaweedFS supplies the local S3-compatible endpoint and Trino is loopback-only; both use local credentials. Production needs TLS, workload identity, scoped buckets/catalogs and audit logs.

Flink bounds out-of-order time, dedupe state and window settings, quarantines invalid/late events, and protects Redis with atomic timestamp compare/set. Redis now requires authentication and is loopback-only. Production needs TLS, secret rotation and ACL-separated identities.

Spark/dbt use fixed SQL and storage locations; no request-controlled shell or SQL construction was found. Data volume caps remain operational safeguards rather than adversarial quotas.

Airflow 3.3.2 runs as UID 50000 with LocalExecutor and no Docker socket. It can call only authenticated, internal, fixed-command Spark and dbt runners with concurrency, timeout and output bounds. SeaweedFS 4.50 replaces the archived MinIO server after a hash-verified copy into a new volume; the original volume is preserved. These local controls do not replace workload identity, network policy or Kubernetes-native job execution in production.
