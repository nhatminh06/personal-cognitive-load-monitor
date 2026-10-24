# Security findings

| ID | Severity | Component | Impact | Remediation / verification | Status |
|---|---|---|---|---|---|
| SEC-001 | High | FastAPI routes | Unauthenticated production prediction, model metadata, ingestion or feature retrieval | Shared constant-time API-key dependency; production missing/blank key fails closed; HTTPX regression tests | Remediated |
| SEC-002 | High | Model loading | Substituted joblib can execute code | Production requires matching `MODEL_SHA256`; missing/mismatch tests | Remediated; signing deferred |
| SEC-003 | High | Airflow dev profile | Docker socket grants daemon-equivalent host authority | Explicit `orchestration-dev`, disabled by default, read-only repo mounts, excluded from Helm | Accepted development-only risk |
| SEC-004 | High | CI/GCP | Broad OIDC/token scope and deployable feature refs | Per-job permissions, main-only manual deploy, protected environment, validated inputs, ref-bound WIF | Remediated; cloud policy unverified |
| SEC-005 | Medium | Kafka/Flink DLQ | Poison records could restart streaming and leak payloads | Strict Flink validation; digest/size-only Python and Java quarantine | Remediated |
| SEC-006 | Medium | HTTP boundary | Oversized body and browser embedding/XSS exposure | 1 MiB streaming cap and CSP/frame/content/referrer headers | Remediated |
| SEC-007 | Medium | Local services | Kafka/MinIO/Trino/Redis/Flink/observability reachable beyond host | All published development ports bind `127.0.0.1` | Remediated |
| SEC-008 | Medium | Redis | Unauthenticated feature store | Password-enabled Redis, authenticated Flink and default local client URL | Remediated; TLS deferred |
| SEC-009 | Medium | Dependencies | Published vulnerabilities in locked transitive packages | Fixed releases selected; one no-fix DVC-only diskcache pickle advisory documented | Remediated with accepted Low residual risk |
| SEC-010 | Medium | Container build | MLflow URI/secrets accepted as build args; mutable `latest` publication | Model downloaded before build, build args removed, immutable SHA tag only | Remediated |
| SEC-011 | Medium | Kubernetes networking | NetworkPolicy allows broad namespace ingress and internet egress | Documented as cloud blocker pending actual controller/DNS/KServe topology | Open, cloud-deferred |
| SEC-012 | Low | GitHub Actions supply chain | Actions used mutable major tags | Existing major versions resolved from official repositories and pinned to immutable commits | Remediated |
| SEC-013 | Low | Abuse controls | No in-process rate limiter | Body/time bounds exist; configure ingress rate/connection limits in deployment | Cloud-deferred |
| SEC-014 | Informational | Authorization model | API key is single-tenant, not per-user object authorization | Explicitly documented; no multi-tenant claim | Accepted |

No CVSS numbers are assigned because deployment reachability and compensating controls are not yet known.
