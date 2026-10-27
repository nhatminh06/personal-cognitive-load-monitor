# Module I local verification

The current source-readiness review adds a separate Knative-mode KServe overlay,
explicit KPA scale-to-zero settings, bounded HPA behavior, a protected manual
Module I deployment workflow and a fail-closed evidence validator. These are
offline/static results until the authorization gates in `final-acceptance.md`
are satisfied. Historical evidence below retains its original date and scope.

On 2026-10-27, **341 Python tests passed in 45.26 seconds with 88.89%
coverage**. Ruff, scoped MyPy, Helm lint, Standard and Knative GKE renders,
workflow YAML parsing and Terraform formatting passed. The 41 focused Module I
tests cover deployment-mode selection, KPA scale-to-zero values, HPA target and
bounds, gateway authentication/ClusterIP isolation, CI dependencies, protected
manual deployment, immutable images, model identity/digests, context guards,
evidence completeness and exclusive report creation.

Read-only DVC status completed and reported the pre-existing modified
`data/processed/module3/training_manifest.json` dependency; it was not changed
or reproduced. Terraform validation was attempted but the installed Google
provider could not complete its local plugin handshake. Actionlint, Gitleaks
and Trivy were unavailable locally. No containers, Kubernetes resources,
Terraform state, model metadata, images or cloud resources were touched.

Verified on 2026-10-23 on branch `feature/cogniflow-module1-foundation`. No cloud resources or remote deployments were used.

## Verified

- **Tests:** `42 passed`; coverage **88.41%** with `--cov-fail-under=81` (strictly greater than 80%).
- **Quality:** Ruff passed; MyPy passed for all seven API source files; `git diff --check` passed.
- **DVC:** two consecutive `dvc repro` runs reported all three stages unchanged and up to date.
- **Notebooks:** all four notebooks executed in place with the `python3` kernel; every code cell has an execution count and no error output. Version 4 of `cognitive-load-classifier` is `READY`, run `f701a0ac02b241558dfd943dbc6d9508`. Scores only measure fidelity to synthetic proxy rules.
- **Docker:** image `sha256:39143ed8c76fe657098c33000a4d9c1a6d4e869ce6e70d516cf54f0bd21d4eb8` built and runs as `appuser`. Demo-rule and packaged local-model requests both returned `is_fallback=false` with their explicit source. KServe mode without an endpoint returned 503 rather than falling back.
- **Observability:** Prometheus target `api:8000` was `up` and scraped LOW/HIGH prediction series. Loki returned structured `/predict` events. Tempo returned trace IDs for service `cognitive-load-api`. Grafana was healthy and provisioned the Cognitive Load API dashboard with metric, log, and trace panels. The stack was shut down afterward.
- **Authentication:** disposable NGINX 1.27 returned `401` without Basic Auth and `200` with a local-only credential. The generated htpasswd remained under `/tmp`, not in Git.
- **Infrastructure:** Helm lint passed; default, local, and GKE values rendered 7, 5, and 9 resources. The standalone KServe YAML and all rendered YAML parsed successfully. Terraform format and validation passed without plan/apply.
- **Secrets:** tracked files were scanned for common private-key and provider-token patterns and suspicious assignments; no credential was found.

## Failed or unavailable

- `kubectl --dry-run=client` could not perform schema discovery without a live API server. This is not runtime Kubernetes evidence.
- UI/UX Pro Max and a browser automation engine were not installed. Responsive CSS, keyboard focus, native validation, loading, API-error and status states were source-reviewed; visual/assistive-technology QA remains manual.
- Semantic Graphify labeling was unavailable because no Gemini key is configured. Graphify's code graph and traversal queries ran successfully; Terraform nodes were omitted because its optional HCL parser is absent.
- Local KServe/Knative runtime verification was skipped: the host had 15 GiB RAM, about 4.9 GiB available, and 14 GiB swap already used. Starting an isolated serving cluster was not safe.

## Cloud-deferred

GKE creation, Workload Identity, managed ingress, external secrets, live KServe/Knative scale-to-zero, HPA behavior under load, GitHub Actions, manual deployment, and hosted observability require the final deployment environment. No Terraform apply, GCP provisioning, commit, push, or PR occurred.

## Resource-safe commands

```bash
mkdir -p /tmp/cogniflow-observability
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose -f infra/observability/docker-compose.observability.yml up -d
curl http://localhost:8001/health
docker compose -f infra/observability/docker-compose.observability.yml down

UV_CACHE_DIR=/tmp/cogniflow-uv-cache uv run pytest src/tests -q --cov=src --cov-fail-under=81
DVC_SITE_CACHE_DIR=/tmp/cogniflow-dvc UV_CACHE_DIR=/tmp/cogniflow-uv-cache uv run dvc repro
make notebooks
helm lint ./helm/cognitive-load-monitor
```

The observability test used six containers plus one short-lived NGINX container. All were stopped; `docker ps` was empty afterward. The final image size was about 2.29 GB, an optimization opportunity before production distribution.
