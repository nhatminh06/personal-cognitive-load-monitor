# Architecture threat model

## Assets and boundaries

The protected assets are API keys, pseudonymous session events, online features, Bronze/Delta objects, model artifacts and digests, MLflow/DVC provenance, CI OIDC identity, Kubernetes credentials, and observability data.

| Boundary | Main STRIDE risks | Enforced control / remaining requirement |
|---|---|---|
| Browser → FastAPI | spoofing, tampering, DoS, disclosure | Production API key, Pydantic bounds, 1 MiB body cap, security headers; single-tenant only |
| FastAPI → Kafka | spoofing, replay, broker outage | validated schema, all acknowledgements, idempotent producer, bounded timeouts; local plaintext only |
| Kafka → consumers | poison data, replay, DLQ leakage | consumers validate again, bounded dedupe, manual commit, digest-only DLQ metadata |
| Consumer → MinIO | object tampering, credential theft | deterministic keys, checksum metadata, commit after durable write; local credentials and plaintext network only |
| Spark → Delta → Trino/dbt | schema corruption, unauthorized queries | explicit validation/merge keys and local loopback ports; production IAM/TLS is deferred |
| Airflow → Docker daemon | elevation to host control | isolated `orchestration-dev` profile, deliberate opt-in, no cloud chart reference; risk remains when enabled |
| Flink → Kafka/Redis | poison messages, stale overwrite | schema/range validation, invalid/late quarantine, dedupe state, atomic timestamp compare/set, Redis auth |
| App → MLflow/model/KServe | artifact substitution, unsafe deserialization, SSRF/outage | CI selects explicit registry version; production joblib needs SHA-256; KServe URL is operator configuration and fails closed |
| GitHub Actions → GHCR/GCP | token abuse, input injection, unintended deploy | per-job token scope, validated input, main-only manual deploy, environment gate, branch-bound WIF |
| NGINX/Ingress → API | bypass, plaintext | API enforces its own auth; production TLS, rate limits and managed secret are deployment requirements |

Graphify (542 nodes) confirmed `main.py`/`api.py` as the HTTP trust-boundary hubs, `kafka.py` as the durability/quarantine bridge, `model_client.py` as the artifact/KServe boundary, and `SessionFeatureJob.RedisFeatureSink` as the streaming state boundary. This directed the fixes to shared boundary code instead of endpoint-by-endpoint duplication.

## Critical attack paths

1. Internet → unauthenticated prediction/feature/event route → compute or session-data access: remediated with shared fail-closed production authentication.
2. Direct Kafka publisher → malformed event → Flink restart loop or invalid feature: remediated with pre-watermark validation and quarantine.
3. Registry/storage compromise → malicious joblib → code execution: reduced by mandatory production digest verification; artifact signing remains cloud-deferred.
4. Malicious DAG → Docker socket → host control: not eliminated locally; isolated as an explicit development-only profile.
5. Workflow dispatch from an unprotected ref → GCP identity: remediated by main-only job condition and WIF subject condition.
