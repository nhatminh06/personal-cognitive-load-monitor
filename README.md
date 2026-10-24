# Personal Cognitive Load & Focus Monitoring System

An end-to-end **MLOps** demonstration: DVC data versioning → MLflow model
tracking/registry → FastAPI pre/post-processing API → Docker → Helm → GKE →
KServe → Prometheus/Grafana/Loki/Tempo → Evidently drift monitoring, all
wired through a coverage-gated, test → build → manual-deploy CI/CD pipeline.

> **This is not a medical, psychological, neurological, workplace-surveillance,
> or diagnostic system.** All data is synthetic (see
> [`docs/data-card.md`](docs/data-card.md)). Predictions should not drive any
> real decision about a real person. See
> [`docs/responsible-use.md`](docs/responsible-use.md).

## Current verification status

Not every requirement below has been run against a live cloud cluster — this
README says exactly which is which. Full detail, with the actual command run
and its output, is in [`docs/requirement-matrix.md`](docs/requirement-matrix.md)
and [`docs/verification.md`](docs/verification.md); do not take a single
"✅ Complete" claim at face value anywhere in this repo — check those two files.

| Status label | Meaning |
|---|---|
| ✅ Verified locally / in CI | Actually executed and observed passing. |
| 🧪 Statically validated | Config/manifest passed a linter or `helm template`/`terraform validate`, not run live. |
| 🚧 Implemented, not execution-verified | Code exists and is reasoned correct; no live run performed. |
| ⛔ Blocked by environment | Cannot verify from this environment (no cloud credentials / Docker daemon / GPU / etc). |

## Table of Contents

1. [Current verification status](#current-verification-status)
2. [System overview](#system-overview)
3. [High-level architecture](#high-level-architecture)
4. [Course requirement mapping](#course-requirement-mapping)
5. [Repository structure](#repository-structure)
6. [Data and model](#data-and-model)
7. [Four-notebook experiment workflow](#four-notebook-experiment-workflow)
8. [Local installation](#local-installation)
9. [Tests and coverage](#tests-and-coverage)
10. [Inference modes](#inference-modes)
11. [MLflow and DVC](#mlflow-and-dvc)
12. [Docker build](#docker-build)
13. [Cloud Kubernetes deployment](#cloud-kubernetes-deployment)
14. [Helm deployment](#helm-deployment)
15. [NGINX gateway and authentication](#nginx-gateway-and-authentication)
16. [FastAPI HPA](#fastapi-hpa)
17. [KServe serving and scale-to-zero](#kserve-serving-and-scale-to-zero)
18. [Metrics, drift, tracing, logging](#metrics-drift-tracing-logging)
19. [CI/CD](#cicd)
20. [Known limitations](#known-limitations)
21. [Demo video](#demo-video)
22. [Submission](#submission)
23. [License](#license)

## System overview

The API predicts one of three synthetic cognitive-load levels — `LOW`,
`MEDIUM`, `HIGH` — from four inputs: focus minutes, distraction minutes,
tasks due, and hours to deadline. The point of the project is the pipeline
around that toy model, not the model itself; see
[`docs/model-card.md`](docs/model-card.md) for exactly what the reported
accuracy does and does not demonstrate.

## High-level architecture

```text
Developer
  -> git push (feature branch)
  -> GitHub Actions: test (Pytest, coverage > 80%)              [Verified in CI]
       -> build (train -> register+pull from MLflow             [Verified in CI]
                 -> Docker image -> push to GHCR)
       -> deploy (workflow_dispatch only, Helm to GKE)           [Implemented, not executed]

Client -> NGINX Ingress + Basic Auth -> FastAPI (HPA-scaled)     [Statically validated]
                                            |
                                            +-> INFERENCE_MODE: auto | rule | local_model | kserve
                                                  (kserve -> KServe InferenceService, scale-to-zero annotated)

Observability: FastAPI/K8s -> Prometheus -> Grafana; FastAPI -> Loki; FastAPI -> Tempo
  [all implemented; not started/executed in the most recent verification pass]

Data/model: DVC (generate_data -> train_model -> drift_report) -> MLflow -> Evidently
  [Verified locally: dvc repro is reproducible — a second run reports no changes]
```

Full narrative version, including why an explicit `INFERENCE_MODE` exists and
the GHCR-vs-Artifact-Registry decision, is in
[`docs/architecture.md`](docs/architecture.md).

## Course requirement mapping

Condensed table — see [`docs/requirement-matrix.md`](docs/requirement-matrix.md)
for the full 27-item table with evidence per item.

| Requirement | Implementation | Status |
|---|---|---|
| Python | `src/`, `scripts/` | ✅ |
| CI/CD: test → build → deploy | `.github/workflows/ci-cd.yaml` | ✅ Verified in CI |
| Pytest | `src/tests/` (70 tests) | ✅ Verified locally |
| Coverage > 80% | `--cov-fail-under=80` | ✅ 99.22% measured this pass |
| Build auto after coverage gate | `build` job `needs: test` | ✅ Verified in CI |
| Deploy manual trigger | `workflow_dispatch` only | ✅ Verified in CI |
| FastAPI pre/post-processing API | `src/preprocessing_api/main.py` | ✅ Verified locally |
| Kubernetes HPA | `helm/.../templates/hpa.yaml` | 🧪 Statically validated |
| KServe model serving | `helm/.../inferenceservice.yaml`, `kserve/inferenceservice.yaml` | 🧪 Statically validated |
| KServe scale-to-zero | `autoscaling.knative.dev/min-scale: "0"` | 🧪 Annotation present; **not proven** — see requirement matrix item 14 |
| NGINX gateway + auth | Helm `Ingress` + Basic Auth `Secret` | 🧪 Statically validated |
| IaC provisions Kubernetes | `infra/terraform/gke/` | 🧪 `fmt`/`init`/`validate` pass; never applied |
| Kubernetes on cloud | GKE (Terraform) | ⛔ Blocked — no `gcloud`/GCP credentials in this environment |
| MLflow tracking/registry | `scripts/train_model.py` | ✅ Verified in CI + locally |
| DVC data/pipeline versioning | `dvc.yaml`, `params.yaml`, `dvc.lock` | ✅ Verified locally (reproducible) |
| Model pulled from MLflow into build image | CI `build` job | ✅ Verified in CI |
| Helm deployment | `helm/cognitive-load-monitor/` | ✅ `helm lint`/`helm template` pass |
| Prometheus + Grafana | `/metrics`, `infra/observability/{prometheus,grafana}` | 🚧 Implemented, not started this pass |
| Evidently drift dashboard | `scripts/generate_drift_report.py` | ✅ Verified locally (real Evidently output, not the fallback) |
| Tempo tracing | `observability.py`, `infra/observability/tempo` | 🚧 Implemented, not started this pass |
| Loki logging | structured logs, `infra/observability/loki` | 🚧 Implemented, not started this pass |
| Four notebooks | `notebooks/01_eda.ipynb` … `04_prepare_for_deployment.ipynb` | ✅ Valid, contain real executed output |
| Feature branch + PR workflow | this work is on `feature/full-fsds-mlops` | ✅ |
| Topic ≠ house-price/OCR | cognitive-load classification | ✅ |

## Repository structure

```text
personal-cognitive-load-monitor/
├── .github/workflows/ci-cd.yaml          # Test, Docker build, manual Helm deploy
├── Dockerfile
├── LICENSE
├── Makefile
├── README.md
├── dvc.yaml                              # DVC pipeline (generate_data -> train_model -> drift_report)
├── dvc.lock                              # DVC reproducibility lock (generated by `dvc repro`)
├── params.yaml                           # Data/train hyperparameters, wired into dvc.yaml's params:
├── pyproject.toml
├── data/{raw,processed,features}/
├── docs/
│   ├── architecture.md
│   ├── requirement-matrix.md
│   ├── verification.md
│   ├── cloud-deployment.md
│   ├── demo-script.md
│   ├── model-card.md
│   ├── data-card.md
│   ├── responsible-use.md
│   └── submission_checklist.md
├── helm/cognitive-load-monitor/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── deployment.yaml
│       ├── hpa.yaml
│       ├── ingress.yaml
│       ├── inferenceservice.yaml
│       ├── servicemonitor.yaml
│       └── ...
├── infra/
│   ├── observability/                    # Local Prometheus/Grafana/Loki/Tempo stack
│   └── terraform/gke/                    # GKE cloud Kubernetes IaC
├── kserve/inferenceservice.yaml          # Standalone KServe example
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_data_processing.ipynb
│   ├── 03_model_training.ipynb
│   └── 04_prepare_for_deployment.ipynb
├── scripts/
│   ├── deploy.sh
│   ├── download_model_from_mlflow.py     # Pulls a model version from MLflow; writes a manifest sidecar
│   ├── generate_drift_report.py
│   ├── local_smoke_test.sh
│   └── train_model.py
└── src/
    ├── data_generator.py
    ├── preprocessing_api/
    │   ├── main.py                       # FastAPI app, INFERENCE_MODE, /ready, /model-info
    │   ├── model_client.py                # KServe + local-model clients, readiness checks
    │   ├── features.py                   # Shared feature engineering (training + serving)
    │   ├── observability.py
    │   ├── schemas.py
    │   └── service.py                    # Deterministic rule engine
    └── tests/
        ├── conftest.py
        ├── test_api.py
        ├── test_model_client.py
        └── test_observability.py
```

## Data and model

All data is synthetic; the training label is generated by the same
deterministic formula the API uses as its rule-based fallback. This means
model accuracy measures how well the model reproduces a known rule, **not**
real-world predictive validity. Full explanation, reproducibility details,
and honest metrics: [`docs/data-card.md`](docs/data-card.md) and
[`docs/model-card.md`](docs/model-card.md).

## Four-notebook experiment workflow

```text
notebooks/01_eda.ipynb                  — exploratory data analysis
notebooks/02_data_processing.ipynb      — cleaning, feature engineering, train/test split
notebooks/03_model_training.ipynb       — training and evaluation
notebooks/04_prepare_for_deployment.ipynb — model export/deployment preparation
```

All four are valid, openable notebooks (`nbformat.validate()` passes) and
contain real executed output from a prior run. No notebook-execution tool
(`nbmake`/`nbconvert --execute`) was available to re-run them top-to-bottom
in the most recent verification pass — see
[`docs/verification.md`](docs/verification.md).

## Local installation

This repository is **uv-first**.

```bash
# macOS
brew install uv
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync --all-extras
```

Run the API locally (default `INFERENCE_MODE=auto`, no model file needed —
falls through to the deterministic rule engine):

```bash
uv run uvicorn preprocessing_api.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
curl -X POST http://127.0.0.1:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 3, "hours_to_deadline": 24}'
# {"cognitive_load_level":"LOW"}

curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8000/model-info
curl http://127.0.0.1:8000/metrics
```

## Tests and coverage

```bash
uv run pytest src/tests \
  --cov=src/preprocessing_api \
  --cov-report=term-missing \
  --cov-fail-under=80
```

Or `make test`. Most recent local run: **70 passed, 99.22% coverage**
(re-run this yourself — do not trust a number in a README that could go
stale; `docs/verification.md` records when this was last measured).

Tests use exact-value assertions for the deterministic rule engine (verified
against the actual formula, not assumed — one pre-existing test's input was
found to produce a different level than its name claimed, and was fixed),
mocked KServe/local-model backends (no real network calls), and cover every
`INFERENCE_MODE` combination including explicit-mode 503 responses and the
opt-in `ALLOW_RULE_FALLBACK` path.

## Inference modes

`INFERENCE_MODE` (env var, default `auto`):

| Mode | Behavior | `/ready` reflects |
|---|---|---|
| `rule` | Deterministic formula only, no model | Always ready |
| `local_model` | Loads `models/cognitive_load_model.joblib` (path from `MODEL_PATH`) | Whether the artifact loads |
| `kserve` | Forwards to `KSERVE_PREDICT_URL` | A lightweight reachability check |
| `auto` (default) | Tries kserve → local_model → rule, **silently** | Always ready (rule always answers) |

`auto` is the local-demo/CI default and matches this project's original
behavior; it is documented here as **not** the recommended setting for a real
deployment, because a caller cannot tell which backend actually answered
without checking `/metrics`. For a real deployment, set an explicit mode; if
the selected backend is unavailable, `/predict` returns `503` rather than
silently substituting the rule engine, unless `ALLOW_RULE_FALLBACK=true` is
also set (in which case the substitution is still labeled distinctly —
`rule_fallback_after_error` — in the recorded Prometheus metric).

`GET /model-info` reports the active mode, whether KServe/the local model are
currently usable, and the model artifact's provenance manifest (written by
`scripts/download_model_from_mlflow.py`) if one exists.

## MLflow and DVC

Train and register a model:

```bash
uv run --extra dev python scripts/train_model.py \
  --input data/raw/sample_data.csv --output models/cognitive_load_model.joblib
```

Hyperparameters (`test_size`, `random_state`, `n_estimators`) and data
generation parameters (`n_samples`, `seed`, `reference_date`) come from
`params.yaml` by default — override with CLI flags if needed.

Run the full DVC pipeline:

```bash
uv run --extra dev dvc dag
uv run --extra dev dvc repro
```

Verified reproducible: running `dvc repro` a second time with no changes
reports `Data and pipelines are up to date` for all three stages (fixed a
`datetime.now()` non-reproducibility bug — see
[`docs/data-card.md`](docs/data-card.md)).

`.dvc/config` points at a placeholder S3 bucket
(`s3://CHANGE_ME_DVC_BUCKET/...`); configure a real remote before any
`dvc push`:

```bash
uv run --extra dev dvc remote modify storage url s3://YOUR_BUCKET/personal-cognitive-load-monitor
```

## Docker build

```bash
docker build -t cognitive-load-api:local .
docker run --rm -p 8000:8000 cognitive-load-api:local
```

Build while pulling a specific model version from a **persistent** MLflow
server (CI instead uses a job-scoped ephemeral server — see
[`docs/model-card.md`](docs/model-card.md) for the distinction):

```bash
docker build \
  --build-arg MLFLOW_TRACKING_URI=http://YOUR_MLFLOW_SERVER:5000 \
  --build-arg MODEL_URI=models:/cognitive-load-classifier/1 \
  -t cognitive-load-api:mlflow .
```

Docker build/run was not executed in the most recent verification pass (no
Docker daemon running in that environment) — see
[`docs/verification.md`](docs/verification.md). `hadolint Dockerfile` was run
and found no blocking issues.

## Cloud Kubernetes deployment

Full step-by-step guide, including cost notes and teardown:
[`docs/cloud-deployment.md`](docs/cloud-deployment.md). Summary:

```bash
cd infra/terraform/gke
cp terraform.tfvars.example terraform.tfvars   # set project_id, github_repository
terraform init && terraform plan && terraform apply
gcloud container clusters get-credentials $(terraform output -raw cluster_name) \
  --region $(terraform output -raw cluster_location)
```

**This has not been run against a real GCP project** — no `gcloud`/cloud
credentials were available in the environment this was verified from.
`terraform fmt -check`, `init -backend=false`, and `validate` all pass.

## Helm deployment

```bash
helm lint helm/cognitive-load-monitor
helm template cognitive-load-monitor helm/cognitive-load-monitor \
  --namespace cognitive-load \
  --set image.repository=ghcr.io/nhatminh06/personal-cognitive-load-monitor/cognitive-load-api \
  --set image.tag=<commit-sha> \
  --set ingress.hosts[0].host=cognitive-load.example.com \
  --set kserve.storageUri=gs://YOUR_BUCKET/models/cognitive-load-classifier
```

Both pass; renders all 10 expected resource kinds (see
[`docs/verification.md`](docs/verification.md)).

**Do not deploy with `image.tag=latest`** — pin the commit SHA CI built. For
a first deploy without KServe/Prometheus Operator installed, also pass
`--set kserve.enabled=false --set serviceMonitor.enabled=false --set config.enableTracing="false"`
(see [`docs/cloud-deployment.md`](docs/cloud-deployment.md) for why).

## NGINX gateway and authentication

The Helm chart's `Ingress` uses `ingressClassName: nginx` and
`nginx.ingress.kubernetes.io/auth-type: basic` against a Kubernetes `Secret`.

**Before any real deployment**, generate a new credential — do not use the
chart's demo default:

```bash
htpasswd -nb admin 'YOUR_STRONG_PASSWORD'
# then: --set-string basicAuth.auth='admin:GENERATED_HASH_HERE'
```

Basic Auth without TLS sends credentials base64-encoded, not encrypted. This
project does not configure TLS; treat any deployment following this README
as a development/demo configuration, not internet-facing production, unless
you add a real certificate.

## FastAPI HPA

`helm/.../templates/hpa.yaml` targets the API `Deployment` on CPU
utilization (`autoscaling/v2`). Renders correctly via `helm template` (see
above). Actual scale-up/scale-down behavior under load has not been observed
against a live cluster in this verification pass — see
[`docs/requirement-matrix.md`](docs/requirement-matrix.md) item 12.

## KServe serving and scale-to-zero

`helm/.../templates/inferenceservice.yaml` and the standalone
`kserve/inferenceservice.yaml` both set
`autoscaling.knative.dev/min-scale: "0"`. **This annotation alone does not
prove scale-to-zero works** — that requires the cluster to run KServe in
Knative/serverless mode, which this repository does not install or verify.
Treat this requirement as "manifest expresses the intent," not "verified
capability," until it has actually been run against a cluster with KServe's
serverless mode installed (see
[`docs/cloud-deployment.md`](docs/cloud-deployment.md#extending-this-deployment)).

## Metrics, drift, tracing, logging

Local observability stack:

```bash
cd infra/observability
docker compose -f docker-compose.observability.yml up -d
```

```text
Grafana:    http://localhost:3000  (admin/admin — change before any shared use)
Prometheus: http://localhost:9090
Loki:       http://localhost:3100
Tempo:      http://localhost:3200
```

The API exposes Prometheus metrics at `/metrics` with bounded labels only
(route, status, prediction class, inference source — never raw input values
or identifiers).

Drift dashboard:

```bash
uv run --extra dev python scripts/generate_drift_report.py \
  --reference data/processed/train.csv \
  --current data/processed/test.csv \
  --output reports/evidently/data_drift.html
```

Open `reports/evidently/data_drift.html`. Verified this pass to be genuine
Evidently output (previously silently fell back to a hand-rolled HTML table
because the script targeted a pre-0.4 Evidently API against a
0.7.x-resolving dependency pin — fixed; see
[`docs/verification.md`](docs/verification.md)).

The local observability compose stack was **not started** in the most recent
verification pass, so Prometheus scrape health, Grafana panels, Tempo
traces, and Loki logs were not freshly observed — see the requirement matrix
for exact status per component.

## CI/CD

`.github/workflows/ci-cd.yaml`:

1. `test`: Pytest + `--cov-fail-under=80`, `contents: read` only.
2. `build` (needs `test`, skipped on PRs): starts a job-scoped ephemeral
   MLflow server, trains, registers a model version, downloads that exact
   version back (`REQUIRE_MODEL=true` — fails the build rather than
   silently substituting a stale local artifact), builds and pushes to GHCR
   tagged with the commit SHA and `:latest`. Permissions:
   `contents: read, packages: write` only.
3. `deploy` (needs `build`, `workflow_dispatch` only): authenticates to GCP
   via Workload Identity Federation, deploys with Helm. Permissions:
   `contents: read, id-token: write` only.

Job-level permissions were tightened this pass — previously all three jobs
inherited `packages: write` and `id-token: write` from a workflow-level
block, though only `build`/`deploy` respectively need them.

Required GitHub secrets for a real cloud deploy:
`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`,
`GKE_CLUSTER`, `GKE_LOCATION`, `KSERVE_STORAGE_URI`, `APP_HOST`. (Optional:
`MLFLOW_TRACKING_URI`/`MLFLOW_MODEL_URI` for a persistent MLflow server at
build time — the ephemeral server above already satisfies the "pull from
MLflow" requirement without them.)

## Known limitations

- All data and labels are synthetic; the label is derived from the same rule
  the API's fallback uses — see [`docs/data-card.md`](docs/data-card.md).
- No real GCP deployment has been performed from this environment; cloud
  items in the requirement matrix are statically validated, not live-verified.
- KServe scale-to-zero is annotated but not proven (needs a real cluster with
  the correct KServe networking mode).
- Local observability stack (Prometheus/Grafana/Loki/Tempo) was not started
  in the most recent verification pass.
- Notebooks were not re-executed top-to-bottom this pass (no `nbmake`/
  `nbconvert` available in this environment); they are valid and contain
  real prior output.

## Demo video

Not recorded. A ready-to-follow script exists at
[`docs/demo-script.md`](docs/demo-script.md) for whenever one is; a link
will be added here once a recording exists.

## Submission

Workflow: `main` (with README) → feature branch → commits → PR into `main`
→ CI checks → (left open for grading, not squash-merged by this work).

This submission's branch: `feature/full-fsds-mlops`.
PR: https://github.com/nhatminh06/personal-cognitive-load-monitor/pull/3
Full submission checklist: [`docs/submission_checklist.md`](docs/submission_checklist.md).

## License

[MIT](LICENSE) — Copyright (c) 2026 Minh Pham.
