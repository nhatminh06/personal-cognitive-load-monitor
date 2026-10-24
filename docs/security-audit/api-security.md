# API security

Sensitive endpoints are `/predict`, `/model-info`, `/events`, and `/features/{session_id}`. In `APP_ENV=production`, absent or whitespace configuration returns 503 and absent/wrong credentials return 401. Comparison is constant-time. Health/readiness/metrics stay unauthenticated for probes; NetworkPolicy and service topology must keep metrics internal.

Pydantic forbids extra event fields and bounds durations, tasks, identifiers, versions and timestamps. Middleware rejects declared or streamed bodies over 1 MiB. CSP, clickjacking, MIME-sniffing and referrer headers are present. The UI uses text-safe DOM updates and no cookie authentication, so CSRF is not applicable.

This is explicitly a single-tenant API-key boundary. It does not establish user identity or prevent one authorized client from reading another session. Multi-tenancy requires identity claims plus session ownership enforcement, not another shared key.

Ingress should provide TLS, request/connection rate limits and key rotation. Application and backend timeouts remain bounded and unavailable inference never silently falls back.
