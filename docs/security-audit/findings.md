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
| SEC-015 | High | GitHub Actions | Persisted checkout credentials, build-job caching and direct expression interpolation increased token/artifact risk | Disabled credential persistence and publishing-job cache; moved image tag through `env`; actionlint/zizmor reruns clean | Remediated |
| SEC-016 | Medium | Module II Dockerfiles | Five service images did not explicitly establish a non-root runtime user | Added explicit users to Airflow, dbt, Flink and MinIO init; persistent-volume compatibility requires local MinIO to retain root | Accepted local-only exception; MinIO is loopback-only and Airflow root is limited to `orchestration-dev` |
| SEC-017 | Medium | API runtime image | Trivy found fixable vendored Python tooling and unfixed base-OS findings | Removed unused pip/setuptools and curl; exact image has 0 Critical and no fixable finding; 44 unfixed Debian High occurrences remain | Accepted pending vendor base updates |
| SEC-018 | High | Airflow development image | Trivy found 34 Critical and 386 High occurrences, including an Airflow advisory fixed only by the 3.3 major line | Profile remains opt-in with no published port, but Docker-socket authority amplifies compromise impact; requires isolated Airflow 3 migration and DAG regression | Open — merge blocker |
| SEC-019 | High | MinIO development image | Trivy found 6 Critical and 66 High occurrences in the pinned 2025 server image; two MinIO advisories have no listed fixed version | Service is loopback-only with development credentials; requires a reviewed current release or managed object-store replacement plus data compatibility tests | Open — merge blocker |
| SEC-020 | Medium | dbt development image | Three fixable High `sqlparse` advisories remain because dbt-core 1.10.15 requires `sqlparse<0.6` | Forced upgrade was rejected by the resolver and reverted; upgrade the dbt compatibility line and rerun transformations | Open |
| SEC-021 | High | GitHub repository controls | `main` has no branch protection and the `production` environment has no reviewers or deployment-branch policy | Workflow code still limits deploy to manual `main`, but a writer can bypass review; configure required PR/checks and production approvers | Open — deployment blocker |

No CVSS numbers are assigned because deployment reachability and compensating controls are not yet known.
