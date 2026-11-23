# CogniFlow MVP local deployment — 2026-11-22

**Primary status: `MVP_RUNNING` (2026-11-22).** The one-service local deployment is healthy at `http://127.0.0.1:18000/focus`. The synthetic session workflow and persistence after an MVP-only restart passed. The remainder of this document preserves the original deployment instructions and historical preflight context; the runtime result below supersedes its earlier pending status.

## V0 runtime result

- The refreshed owner inventory identified nine retained containers. After Docker activation one retained Module I control-plane container unexpectedly started; the owner stopped it. Before the MVP build and after the final restart, all nine original IDs were present and stopped. No retained container was modified by the MVP deployment.
- The dedicated image was built from Git `e9cefee6a99e25cad1bce73b78948398ad5b23b8` plus the uncommitted working tree. Local OCI index ID: `sha256:d4bca2717cbbe10a4ecebc99f986b1f64ffdf1b3651369fc8c39ab35d4c95017`; runtime manifest `sha256:ba0891f3f64a3f5274f677cb306be50a636d1f896eba47bb27a08b8ea13499ae`; config `sha256:0d4d48737f7ca399c14e8da9018f21cc20176ce5882c3482d6140d0bc674ab2c`.
- Trivy 0.76.2 refreshed its vulnerability database on 2026-11-22 and scanned the exact image's Wolfi and Python targets: **0 HIGH, 0 CRITICAL**, exit 0. Ignored raw report: `build/mvp/trivy.json`, SHA-256 `37fb063ee4638d78f48208791ea8659c1e5c4dc4efb39919a84ed09d86374ed6`.
- The API secret remains private, with a read-only ACL for runtime UID 65532. A direct non-root read inside the running container succeeded without printing the value. The MVP-only SQLite volume required one-time ownership initialization for UID 65532; non-root write verification passed.
- `/focus` returned HTTP 200. The synthetic smoke passed health/readiness, unauthenticated rejection, authenticated session creation, six-minute completion, one five-minute window, and `demo_rule` estimate with null model version. The saved session survived an MVP-only container restart; readiness returned healthy afterward.
- Settled sampled use after restart: **0.16% CPU and 159.6 MiB / 768 MiB**. A startup sample reached 100.28% CPU and 58.63 MiB; these are samples, not measured peaks. No browser automation was performed. Effort-rating and timeline behavior retain full-suite test evidence, but were not exercised in the V0 HTTP smoke.
- MVP container `cogniflow-mvp-api-1` is running and healthy. All nine retained containers were stopped at the final Docker inventory check.

Operational commands: `docker compose --project-name cogniflow-mvp --file compose.mvp.yml logs --no-color api` for logs; `docker restart cogniflow-mvp-api-1` for an MVP-only restart; `docker compose --project-name cogniflow-mvp --file compose.mvp.yml down` for shutdown while preserving the volume. Cleanup with `down --volumes` discards the MVP's synthetic SQLite data and requires an explicit owner decision. For remote viewing, use `ssh -L 18000:127.0.0.1:18000 USER@HOST` and open `http://127.0.0.1:18000/focus` locally.

This is a deployment record, not a new readiness milestone. `FROZEN — DEFER_KFP / NO-GO`, `DEFER_SPARK_ENFORCED`, and the KServe deployment restrictions remain unchanged.

## Available functionality

- `/focus`: local focus workspace with authenticated session creation, pause/resume/completion, server-authoritative five-minute windows, effort ratings/corrections, timeline, and SQLite persistence.
- `/health` and `/ready`: liveness and dependency-free readiness.
- `/`: redirects the MVP to the authenticated focus workspace; the legacy prediction page remains available only in development mode.
- `/predict`: authenticated deterministic `demo_rule` result for synthetic inputs only. Responses identify `inference_source=demo_rule`, have no model version, and are not represented as model predictions.
- `/model-info`: reports `demo_rule` and `synthetic_proxy` provenance.
- `/metrics`: local Prometheus-format process/application metrics.
- Synthetic smoke workflow: authentication rejection/acceptance, session creation/completion, persisted window, and explicitly labeled rule estimate.

The focus workspace itself states that model estimates are unavailable and never requests camera access. No personal data or approved model is bundled.

## Explicit exclusions

Spark, KFP, KServe, Kafka, Flink, Redis, Trino, dbt, MLflow, object storage, CV capture, trained-model inference, model approval, Kubernetes, and cloud resources are absent from `compose.mvp.yml`. Their source, tests, manifests, and evidence are preserved. Independent component qualifications are not promoted to an integrated claim.

## Deployment design

| Property | MVP value |
|---|---|
| Project namespace | `cogniflow-mvp` |
| Service/image | `api`; build target `cogniflow-mvp:2026-11-21` |
| Host URL after successful deployment | `http://127.0.0.1:18000/focus` |
| CPU / memory | 1 CPU / 768 MiB limit |
| Temporary storage | 64 MiB `/tmp` tmpfs; read-only root filesystem |
| Persistence | MVP-owned `mvp-data` volume at `/var/lib/cogniflow`; SQLite only |
| Secret | `build/mvp/cogniflow_api_key`, mode 0600, mounted at `/run/secrets/cogniflow_api_key` |
| User / privileges | Dockerfile UID 65532; all capabilities dropped; no-new-privileges; 128 PID limit |
| Exposure | loopback `127.0.0.1:18000` only |
| Restart | `no`; no automatic restart policy |
| Readiness | bounded `/ready` health check, 12 retries, 20-second start period |
| Ownership | project name plus `io.cogniflow.owner=mvp-2026-11-21` labels |

The 768 MiB limit is above the historical C5.3 FastAPI peak of 429.7 MiB. It is a proposed local ceiling, not a fresh runtime measurement. The preflight requires 2 GiB available memory and 4 GiB free disk; the restricted inspection observed about 11.1 GiB available memory, 141.4 GiB repository storage, and 7.5 GiB `/tmp`, but could not query systemd over the sandbox bus. The KFP 12 GiB gate is not applied.

## Image identity and security gate

The Dockerfile pins these build materials:

- uv index `ghcr.io/astral-sh/uv:0.10.0@sha256:78a7ff97cd27b7124a5f3c2aefe146170793c56a1e03321dd31a289f6d82a04f`;
- Wolfi base `cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90`;
- Wolfi Python `3.13.18_git20261115-r1`;
- Python dependency resolution from `uv.lock`.

Historical C5.3 evidence records local FastAPI image `sha256:9609981bd9c775b3937a0d8cf7158c02e786089cd35ce1de5352d90b4ace26c0` at 0 HIGH/0 CRITICAL, but its raw evidence is absent and the current application source has changed. It is not reused as current qualification. The MVP image identity and security status are therefore **UNVERIFIED until built and freshly scanned**. Any HIGH/CRITICAL finding or scanner error stops deployment.

## Validation executed

| Check | Result |
|---|---|
| Frontend locked install | PASS; `npm ci --offline`, one package, zero npm audit findings |
| Frontend typecheck/build | PASS |
| Frontend state tests | PASS; 1 passed |
| MVP deployment/auth/fixture tests | PASS; 5 passed |
| Full application regression | PASS; 714 passed, 2 skipped, 5 warnings, 87.00% coverage |
| Ruff (`src scripts`) | PASS |
| Offline Compose YAML parse and one-service inventory | PASS |
| Git whitespace | PASS |
| Docker/Compose runtime render | NOT RUN; Docker CLI was prohibited before the safety gate |
| Image build and exact-image scan | NOT RUN; owner authorization pending |
| Local startup and synthetic smoke | NOT RUN; owner authorization pending |

The full suite initially demonstrated the sandbox boundary because its loopback tracing test could not create a socket. It was rerun outside that restriction with approval and passed. No Docker, containerd, Kubernetes, or cloud API was contacted.

## Reproducible owner workflow

### 1. Close the Docker activation safety gate

While `docker.service`, `docker.socket`, and `containerd.service` are inactive, run the narrowly scoped, sanitized collector specified in `docs/readiness/module1-mlmd-offline-docker-inventory-2026-11-21.md`. Provide only container ID/name, restart policy and retry count, last-recorded state, explicit manual-stop evidence, and restart-risk classification. Do not print environment, mounts, secrets, or complete configuration files.

Activation is allowed only after review establishes that no retained container can restart. If evidence is missing or ambiguous, stop.

### 2. Create the local secret and run preflight

```bash
install -d -m 0700 build/mvp
python -c 'import secrets; print(secrets.token_urlsafe(32))' > build/mvp/cogniflow_api_key
chmod 0600 build/mvp/cogniflow_api_key
.venv/bin/python scripts/mvp_preflight.py
```

The script does not invoke Docker and fails closed unless all runtime units are inactive. Passing it does not replace review of the sanitized restart inventory.

### 3. Consolidated authorization request

After the inventory passes, authorize this exact action set as one bounded local operation:

1. start `docker.service` (and its required containerd dependency) without enabling either unit;
2. fetch only the two digest-pinned Dockerfile bases if absent;
3. build `cogniflow-mvp:2026-11-21` from `Dockerfile` and record its exact local ID;
4. generate an SBOM and run a complete unsuppressed Trivy OS/language scan, requiring zero HIGH and zero CRITICAL and no scan error;
5. render `compose.mvp.yml`, confirm its one-service inventory, then create only project `cogniflow-mvp`, its labeled network, secret mount, and `mvp-data` volume;
6. wait for readiness, execute `scripts/mvp_smoke.py`, restart only the MVP API once to verify SQLite persistence, sample resource use, and inspect sanitized MVP logs;
7. on any failure, stop/remove only MVP-owned resources; never start, stop, attach to, or modify retained containers or clusters.

No pull, build, container creation, or activation was performed by this milestone.

### 4. Authorized build, scan, deploy, and smoke commands

```bash
sudo systemctl start docker.service
docker image inspect ghcr.io/astral-sh/uv@sha256:78a7ff97cd27b7124a5f3c2aefe146170793c56a1e03321dd31a289f6d82a04f \
  >/dev/null || docker pull ghcr.io/astral-sh/uv@sha256:78a7ff97cd27b7124a5f3c2aefe146170793c56a1e03321dd31a289f6d82a04f
docker image inspect cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90 \
  >/dev/null || docker pull cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90
docker build --pull=false --tag cogniflow-mvp:2026-11-21 --file Dockerfile .
docker image inspect cogniflow-mvp:2026-11-21 --format '{{.Id}}'
trivy image --scanners vuln --severity HIGH,CRITICAL --exit-code 1 \
  --format json --output build/mvp/trivy.json cogniflow-mvp:2026-11-21
trivy image --format spdx-json --output build/mvp/sbom.spdx.json cogniflow-mvp:2026-11-21
docker compose --project-name cogniflow-mvp --file compose.mvp.yml config --quiet
docker compose --project-name cogniflow-mvp --file compose.mvp.yml up --detach --no-build --wait
.venv/bin/python scripts/mvp_smoke.py
docker compose --project-name cogniflow-mvp --file compose.mvp.yml logs --no-color api
docker stats --no-stream cogniflow-mvp-api-1
```

The consolidated authorization explicitly covers retrieving these two immutable digests when absent. Do not substitute a tag or another digest.

### 5. Shutdown and cleanup

Preserve MVP data:

```bash
docker compose --project-name cogniflow-mvp --file compose.mvp.yml down
```

Remove only MVP-owned runtime data and image after explicit confirmation that the synthetic session can be discarded:

```bash
docker compose --project-name cogniflow-mvp --file compose.mvp.yml down --volumes
docker image rm cogniflow-mvp:2026-11-21
```

Do not use prune, broad label deletion, or `--remove-orphans` outside the named MVP project.

## GCP handoff

The existing supported cloud architecture is regional private-node GKE in `us-central1`, Artifact Registry, Secret Manager, Workload Identity, Cloud Logging/Monitoring, budget alerts, and Helm. Reusing it would preserve the container HTTP contract, but it is not the smallest operational footprint for this one-service MVP and its current chart/deployment records are intertwined with deferred KServe controls. Cloud Run would be smaller, but the repository has no qualified Cloud Run infrastructure and the SQLite store would not provide durable multi-instance persistence. No new cloud architecture is introduced here.

Before selecting a target, the owner must decide whether the MVP may be stateless/ephemeral or authorize a supported persistent store and migration. For the existing GKE path, prerequisites are:

- verify project `pnm-cognitive-load`, billing linkage, project number, quotas, and current API state;
- separately authorize billing and the services in `infra/terraform/gke/apis.tf`, including GKE, Artifact Registry, Secret Manager, IAM/STS, Compute, Monitoring, and Billing Budgets;
- review a backend-configured Terraform plan, two-zone `e2-standard-4` cost, deletion protection, NAT, fixed `/32` control-plane access, and the mandatory budget notification channel;
- publish the freshly qualified MVP image to private Artifact Registry by immutable remote digest, with SBOM/provenance/signature evidence; historical local IDs are insufficient;
- store the API key in Secret Manager, use the existing API Workload Identity pattern, TLS ingress/IAP or another reviewed authentication boundary, rate limits, and no public unauthenticated API;
- create an API-only Helm values set that disables KServe/InferenceService and supplies durable session storage; validate it offline and in an authorized disposable namespace before any production claim;
- record rollback to the previous immutable digest and database schema, then destroy test resources through reviewed Terraform/Helm ownership boundaries.

Billing was previously recorded as disabled and all API/billing states remain **UNVERIFIED** because no cloud query was authorized. GCP deployment is a later, separately authorized activity; no API, billing, registry, secret, cluster, or charge was created here.

## Files changed

- `compose.mvp.yml`
- `src/preprocessing_api/security.py`
- `src/tests/test_mvp_deployment.py`
- `scripts/mvp_preflight.py`
- `scripts/mvp_smoke.py`
- `examples/mvp/synthetic-estimate.json`
- this deployment record

## Remaining owner action

Provide the sanitized offline restart-policy inventory. If it proves no automatic restart risk, approve the single consolidated local action set above. The next legitimate result is either `MVP_RUNNING` after the exact image passes its scan and the real synthetic smoke completes, or `MVP_BLOCKED_SECURITY`/`MVP_BLOCKED_ENVIRONMENT` at the first failed gate. Do not initiate another preparation milestone.
