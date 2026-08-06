# Architecture

## System overview

```text
Developer
  -> git push (feature branch)
  -> GitHub Actions: test (Pytest, coverage > 80%)              [Verified in CI]
       -> build (train -> register+pull from ephemeral MLflow    [Verified in CI]
                 -> Docker image -> push to GHCR)
       -> deploy (workflow_dispatch only, Helm to GKE)           [Implemented, not executed]

Client request
  -> NGINX Ingress + Basic Auth                                  [Statically validated]
  -> FastAPI pre/post-processing API (HPA-scaled Deployment)      [Verified locally]
       -> INFERENCE_MODE = auto | rule | local_model | kserve
            - rule:         deterministic formula, no model
            - local_model:  loads models/cognitive_load_model.joblib
            - kserve:       forwards to KServe InferenceService   [Statically validated]
            - auto:         kserve -> local_model -> rule, silently (local/demo default)

Observability (all: implemented, not executed in this pass — see verification.md)
  FastAPI/KServe/Kubernetes -> Prometheus -> Grafana
  FastAPI                   -> Loki (via Promtail)
  FastAPI                   -> Tempo (OTLP traces)

Data / model lifecycle
  DVC (generate_data -> train_model -> drift_report)              [Verified locally,
  MLflow (tracking + registry)                                     reproducible: dvc repro
  reference_data/current_data -> Evidently drift dashboard          run twice = no changes]
```

## Why "auto" inference mode exists and what it means

Before this pass, the API only ever had one behavior: try KServe, then the
local model, then the rule engine, silently, with no way to require a
specific backend or make its absence visible via `/ready`. That is fine for a
local demo (there's always a fallback so the API "just works"), but it means
a caller — or a Kubernetes readiness probe — cannot distinguish "the real
model answered" from "the deterministic formula answered because the model
was missing."

This pass added three **explicit** modes (`rule`, `local_model`, `kserve`)
selected via `INFERENCE_MODE`. In an explicit mode:

- `/ready` reflects that specific backend's real health (model loads? KServe
  reachable?) instead of always reporting healthy.
- `/predict` uses only that backend. If it's unavailable, the API returns
  **503**, not a silently-substituted answer — unless `ALLOW_RULE_FALLBACK=true`
  is set, in which case it still falls back, but the response is labeled
  `rule_fallback_after_error` in the recorded metric so the substitution is
  visible in Prometheus, not hidden.

`INFERENCE_MODE=auto` (the default, unchanged) preserves the original
kserve→local_model→rule chain for local development, tests, and the current
CI pipeline. It is intentionally not what a production Helm values file
should use — see the README's "Inference modes" section for the recommended
production values.

## Deployment topology (as designed, not all of it executed)

- **Cluster**: GKE, provisioned by `infra/terraform/gke/` (validated with
  `terraform fmt`/`init -backend=false`/`validate` this session; never
  applied — no GCP credentials in this environment).
- **Ingress**: NGINX ingress controller (installed separately, not part of
  the app's own Helm chart) routes to the API Service; Basic Auth enforced at
  the ingress via a Kubernetes Secret.
- **API**: `Deployment` + `HorizontalPodAutoscaler` (CPU-based) + `Service`.
- **Model serving**: either the API's own `local_model` mode (joblib artifact
  baked into the image or downloaded at build time from MLflow) or a
  `KServe InferenceService` with `autoscaling.knative.dev/min-scale: "0"`.
  See `docs/requirement-matrix.md` item 14 for why scale-to-zero is not
  treated as proven just because the annotation exists.
- **Observability**: `ServiceMonitor` for Prometheus Operator scraping (only
  renders/applies if the Prometheus Operator CRDs are installed — see the
  README's GCP deployment notes for why this was disabled in the one actual
  deploy this project has documented steps for).

## Registry and image strategy

CI publishes to **GHCR** (`ghcr.io/<owner>/<repo>/cognitive-load-api`), tagged
with the 12-character commit SHA and also `:latest`. Terraform additionally
provisions a **GCP Artifact Registry** repository that CI does not use — a
known, intentional inconsistency: GHCR was chosen because it requires zero
extra CI configuration (uses `GITHUB_TOKEN`), while Artifact Registry stays
available if a future change wants to publish there instead via Workload
Identity Federation (`infra/terraform/gke/github_oidc.tf` already sets up the
federation needed for that). This is documented rather than silently
resolved by deleting either side, per the explicit instruction not to leave
this ambiguous.

**Do not rely on `:latest` for a real deployment** — Helm's default
`image.tag` is `latest` for local convenience, but any real `helm upgrade`
should pin the commit SHA tag CI produced (see README's Helm section and
`docs/cloud-deployment.md`).
