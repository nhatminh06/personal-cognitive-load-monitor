# Data platform security

Kafka is plaintext and unauthenticated only inside the isolated local Compose network; its host listener is loopback-only. Producers require all acknowledgements and idempotence. Consumers validate independently, commit only after handling or durable quarantine, and never copy raw invalid payloads into the DLQ. End-to-end exactly-once is not claimed.

Bronze keys are derived from validated schema date and event UUID digests, not user path fragments. Writes carry SHA-256 metadata and offsets follow durable handling. MinIO and Trino are loopback-only and use local credentials; production needs TLS, workload identity, scoped buckets/catalogs and audit logs.

Flink bounds out-of-order time, dedupe state and window settings, quarantines invalid/late events, and protects Redis with atomic timestamp compare/set. Redis now requires authentication and is loopback-only. Production needs TLS, secret rotation and ACL-separated identities.

Spark/dbt use fixed SQL and storage locations; no request-controlled shell or SQL construction was found. Data volume caps remain operational safeguards rather than adversarial quotas.
