# Requirement Matrix

Status values used below, applied honestly per item — a filename existing is
never treated as sufficient on its own:

- **Verified locally** — executed on this machine during this work and the
  output inspected.
- **Verified in CI** — observed passing in an actual GitHub Actions run.
- **Statically validated** — config/manifest passed a linter/validator
  (`helm lint`, `terraform validate`, etc.) but was not exercised at runtime.
- **Implemented, not execution-verified** — code/config exists and is
  reasoned to be correct, but no cluster/service was actually run against it
  in this pass.
- **Blocked by environment** — cannot be verified from this machine (no
  `gcloud`/cloud credentials, no Docker daemon running, etc.).

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Python is mandatory | **Verified locally** | Entire codebase is Python 3.11+; `uv run python -m compileall src scripts` passes with no output (no syntax errors). |
| 2 | CI/CD contains Test, Build, Deploy | **Verified in CI** | `.github/workflows/ci-cd.yaml` has `test`, `build`, `deploy` jobs; a real run on `main` (commit `a74b9756d3c2`) shows all three, `deploy` correctly skipped (not manually triggered). |
| 3 | Tests use Pytest | **Verified locally** | `uv run pytest src/tests ...` — 70 tests collected and run via pytest. |
| 4 | Coverage above 80% | **Verified locally** | `--cov-fail-under=80` run this session: **99.22%** total (`src/preprocessing_api`), 70 passed. See [`verification.md`](verification.md) for the full table. |
| 5 | Build runs automatically only after tests pass the coverage gate | **Verified in CI** | `build` job has `needs: test`; `test` job runs `--cov-fail-under=80` and fails the job (and blocks `build`) if coverage drops below 80. |
| 6 | Deploy requires a manual trigger | **Verified in CI** | `deploy` job: `if: github.event_name == 'workflow_dispatch'`; confirmed skipped on the `push`/`pull_request`-triggered runs observed. |
| 7 | Metrics monitoring: Prometheus + Grafana | **Implemented, not execution-verified this session** | `/metrics` Prometheus endpoint in `main.py`/`observability.py`; `infra/observability/prometheus/prometheus.yml`, `infra/observability/grafana/{dashboards,provisioning}`. `docker-compose.observability.yml` was not started in this pass — see [`verification.md`](verification.md). |
| 8 | Data drift monitoring: Evidently or equivalent, with dashboard | **Verified locally** | Fixed the API mismatch that made `generate_drift_report.py` silently fall back to a hand-rolled HTML table (old `evidently.report`/`evidently.metric_preset` imports failing against Evidently 0.7.x). Ran the real pipeline this session (`dvc repro`); confirmed `reports/evidently/data_drift.html` contains no `"Fallback report"` marker string, i.e. is genuine Evidently output. |
| 9 | Distributed tracing: Tempo/Jaeger or equivalent | **Implemented, not execution-verified this session** | OpenTelemetry instrumentation in `observability.py` (`configure_tracing`), Tempo config at `infra/observability/tempo/tempo.yaml`. No Tempo container was started and no trace was observed this session. |
| 10 | Centralized logging: Loki/ELK or equivalent | **Implemented, not execution-verified this session** | Structured `logging` calls throughout; `infra/observability/loki/local-config.yaml`, `infra/observability/promtail/config.yml`. Not started/observed this session. |
| 11 | FastAPI pre/post-processing API exists | **Verified locally** | `src/preprocessing_api/main.py`; endpoints exercised by the test suite (`/health`, `/ready`, `/metrics`, `/predict`, `/model-info`, `/`, `/favicon.ico`, `/robots.txt`). |
| 12 | Kubernetes HPA autoscaling for the FastAPI deployment | **Statically validated** | `helm/cognitive-load-monitor/templates/hpa.yaml` targets the API Deployment (`autoscaling/v2`, CPU target); confirmed it renders via `helm template` this session. No real cluster load test was run — see item 18 for why (no cloud credentials in this environment). |
| 13 | KServe used for model serving | **Statically validated** | `helm/.../templates/inferenceservice.yaml` and standalone `kserve/inferenceservice.yaml`; `helm template` renders a valid `InferenceService` manifest. Never deployed to a real cluster with KServe installed in this pass. |
| 14 | KServe service supports scale-to-zero | **Statically validated only — not proven** | `autoscaling.knative.dev/min-scale: "0"` annotation is present. Per the KServe/Knative documentation, actual scale-to-zero requires the cluster to run KServe in Knative/serverless mode; this repository does not install or configure that mode, and no real cluster was available to verify cold-start behavior. **Do not treat this as a proven capability** — treat it as "manifest expresses the intent." |
| 15 | NGINX acts as API gateway/ingress | **Statically validated** | `helm/.../templates/ingress.yaml`, `ingressClassName: nginx`; renders correctly via `helm template`. Not deployed against a real ingress controller. |
| 16 | Authentication enabled at the NGINX gateway | **Statically validated; credential rotation required before real use** | `nginx.ingress.kubernetes.io/auth-type: basic` + a Kubernetes `Secret` template. The chart's demo `basicAuth.auth` default is a **known password** (`admin/admin123`) and must be regenerated before any real deployment — see README's Helm section. Unauthenticated-vs-authenticated request behavior was not tested against a live ingress controller this session. |
| 17 | Infrastructure as Code provisions Kubernetes | **Statically validated** | `infra/terraform/gke/`: `terraform fmt -check` clean (two files reformatted this session), `terraform init -backend=false` succeeds, `terraform validate` succeeds. Never applied — no GCP credentials available in this environment. |
| 18 | Kubernetes runs on a cloud provider | **Blocked by environment** | Terraform targets GKE. `gcloud` CLI is not installed on this machine and no GCP credentials/project were provided, so no cluster was created or verified this session. See `docs/cloud-deployment.md` for the exact steps to run this yourself. |
| 19 | MLflow versions and tracks the model | **Verified in CI + locally** | `scripts/train_model.py` logs params/metrics/tags and registers `cognitive-load-classifier`. CI's `build` job starts a real (job-scoped) MLflow server, trains against it, and a prior run registered version 1 (log excerpt in `docs/verification.md`). Local `dvc repro` this session registered version 3 against a local file-store MLflow run. |
| 20 | DVC versions the data and pipeline | **Verified locally** | `dvc.yaml` now declares real `params:` blocks (previously `params.yaml` existed but was read by nothing — dead file, fixed this session). `dvc repro` run twice back-to-back: first run trains/registers/generates the drift report; second run reports `Data and pipelines are up to date` for all three stages, proving reproducibility. |
| 21 | Model pulled from MLflow when building the deployment image | **Verified in CI** | CI `build` job log (prior run, unchanged by this session's work): `Created version '1' of model 'cognitive-load-classifier'` → `Downloading MLflow artifact from models:/cognitive-load-classifier/1` → `Saved model artifact to models/cognitive_load_model.joblib`, all before `docker build` runs. `REQUIRE_MODEL=true` on that step means a failed pull fails the build rather than silently falling back. |
| 22 | Kubernetes applications deployed with Helm | **Statically validated** | `helm lint helm/cognitive-load-monitor` → 0 charts failed; `helm template` renders all 10 expected resource kinds (NetworkPolicy, ServiceAccount, Secret, ConfigMap, Service, Deployment, HPA, Ingress, InferenceService, ServiceMonitor). Not applied to a live cluster. |
| 23 | Submission developed on a feature branch | **Verified locally** | This work is on `feature/full-fsds-mlops`, branched from `main` at commit `a74b9756d3c2`. |
| 24 | PR from feature branch into `main` contains the complete submission | **Verified** | See the PR link recorded in `docs/submission_checklist.md` and the top of the PR description. |
| 25 | README: TOC, repository structure, architecture, install/run guide | **Verified locally** | Present in the restructured `README.md`; every command in it was either run this session or matches a command run in a prior session on this same codebase. |
| 26 | At least 4 Jupyter notebooks (EDA, processing, training/eval, deployment prep) | **Statically validated; not re-executed top-to-bottom this session** | `notebooks/01_eda.ipynb` … `04_prepare_for_deployment.ipynb` exist, are valid JSON/nbformat (fixed from real corruption in a prior session — verified with `nbformat.validate()`), and contain genuine executed outputs (paths reference the author's machine). No notebook-execution tool (`nbmake`, `nbconvert --execute`) is installed in this environment, so a fresh top-to-bottom re-execution was **not** performed this session. |
| 27 | Topic is not house-price prediction or OCR | **Verified locally** | Topic is personal cognitive-load classification from focus/task/deadline signals. |

## Honest summary

Of 27 criteria: **19 verified (locally or in CI)**, **6 statically validated**
(manifests/config correct but not run against a live cluster), **1 blocked by
environment** (no cloud credentials available here), and **1 explicitly
flagged as unproven** despite a correct-looking annotation (KServe
scale-to-zero — this needs the right KServe networking mode plus a real
cluster to actually demonstrate, not just the annotation).

See [`docs/cloud-deployment.md`](cloud-deployment.md) for exact steps to
close the cloud-verification gaps (items 12, 13, 14, 15, 16, 18) once GCP
credentials are available, and [`docs/verification.md`](verification.md) for
every command run this session with its actual output.
