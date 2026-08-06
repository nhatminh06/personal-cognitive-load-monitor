# Verification Log

Every command below was actually run against this repository. Output is
summarized, not fabricated; full logs are reproducible by re-running the
listed command. See `docs/requirement-matrix.md` for how these map to the
grading criteria.

## Python / tests

| Command | Result | Notes |
|---|---|---|
| `uv sync --all-extras` | Passed | 297 packages resolved, 290 checked (no changes needed at time of this run). |
| `uv run ruff check .` | 9 findings, 0 in modified source files | 2 pre-existing notebook style nits (`F541`, `F811`), 3× `E402` (module import after `sys.path.insert`) in `scripts/train_model.py` and `src/tests/conftest.py` — this is a deliberate, pre-existing pattern (path injection before a local import) common in exactly this kind of script layout, not a new issue introduced here. |
| `uv run python -m compileall src scripts -q` | Passed | No output — no syntax errors in any module. |
| `uv run pytest src/tests --cov=src/preprocessing_api --cov-report=term-missing --cov-fail-under=80` | **Passed** | **70 passed**, **99.22% coverage** (up from 36 tests / 98% before this pass — added real-behavior tests: exact rule-mode outputs including one that caught a mislabeled existing test, INFERENCE_MODE/`/ready`/`/model-info` coverage, KServe/local-model readiness helpers). |

## DVC

| Command | Result | Notes |
|---|---|---|
| `uv run dvc dag` | Passed | `generate_data -> train_model -> drift_report`, as declared. |
| `uv run dvc repro` (1st run) | Passed | Regenerated `data/raw/sample_data.csv`, retrained (registered MLflow version 3 locally), regenerated `data/processed/{train,test}.csv`, `reports/metrics.json`, and a **real** Evidently `reports/evidently/data_drift.html` (confirmed no `"Fallback report"` marker). Created `dvc.lock` for the first time in this repo's history. |
| `uv run dvc repro` (2nd run, no changes) | **Passed — reproducible** | `Stage 'generate_data' didn't change, skipping` / same for `train_model`, `drift_report` / `Data and pipelines are up to date.` This is the concrete fix for the `datetime.now()` non-reproducibility bug (see `docs/data-card.md`). |
| `uv run dvc status` | `Data and pipelines are up to date.` | Confirms the above. |

## Docker

| Command | Result | Notes |
|---|---|---|
| `docker build` / `docker run` smoke test | **Blocked by environment** | Docker daemon is not running on this machine (`docker info` fails). Not executed this session. A prior session validated that `scikit-learn`/`joblib` resolve correctly under `uv sync --no-dev` (the exact install mode the Dockerfile uses), which was the main runtime-dependency risk; full image build/run was not re-verified here. |
| `hadolint Dockerfile` | 4 findings, none blocking | `DL3008` (unpinned `apt-get install curl` version), `DL3059` (consecutive `RUN`, cosmetic), `DL3066` (named non-numeric UID note — expected, the Dockerfile intentionally creates a named `appuser`), `DL3025` (shell-form CMD — intentional, needed for `${PORT}` env-var expansion at container start; JSON-array `CMD` would not expand it). |

## Helm

| Command | Result | Notes |
|---|---|---|
| `helm lint helm/cognitive-load-monitor` | **Passed** | `1 chart(s) linted, 0 chart(s) failed` (one informational note: `icon is recommended`). |
| `helm template ... --set image.tag=test --set ingress.hosts[0].host=... --set kserve.storageUri=...` | **Passed** | Renders all 10 expected resource kinds: NetworkPolicy, ServiceAccount, Secret, ConfigMap, Service, Deployment, HorizontalPodAutoscaler, Ingress, InferenceService, ServiceMonitor. |
| `kubeconform` | **Not run** | Not installed in this environment. |

## Terraform

| Command | Result | Notes |
|---|---|---|
| `terraform -chdir=infra/terraform/gke fmt -check` | Initially failed on 2 files | Fixed with `terraform fmt` (whitespace/alignment only — `apis.tf`, `github_oidc.tf`); re-ran `fmt -check`, now clean. |
| `terraform -chdir=infra/terraform/gke init -backend=false` | **Passed** | Provider plugins resolved; `.terraform.lock.hcl` gained one additional platform hash (this machine's), a normal and safe outcome of running `init` on a new platform. |
| `terraform -chdir=infra/terraform/gke validate` | **Passed** | `Success! The configuration is valid.` |
| `terraform plan` / `apply` | **Blocked by environment** | No `gcloud` CLI installed, no GCP project/credentials available. Never applied — see `docs/cloud-deployment.md`. |

## Observability

| Command | Result | Notes |
|---|---|---|
| `docker compose -f infra/observability/docker-compose.observability.yml config --quiet` | **Not run** | Docker unavailable this session (see above). |
| `promtool check config ...` | **Not run** | `promtool` not installed in this environment. |
| Live Prometheus/Grafana/Loki/Tempo check | **Not run** | Stack was not started this session. Configuration files exist and were inspected but not exercised at runtime. |

## Security / linting tools requested but unavailable in this environment

`actionlint`, `yamllint`, `markdownlint-cli2`, `gitleaks`, `trivy`,
`kubeconform`, `promtool`, `nbmake` are not installed here and were not run.
`hadolint` was available and run (above). Where a tool wasn't available, the
corresponding requirement is marked **Blocked by environment** or **Not
run**, not silently skipped without note.

## Attribution check

```bash
grep -RniE \
  'claude|anthropic|cursor|copilot|generated by ai|made-with|co-authored-by:.*(claude|anthropic|cursor|copilot)' \
  --exclude-dir=.git \
  .
```

Run against the working tree before every commit on this branch. Any match
in a file this branch modifies is treated as a blocker; matches only inside
`.git`'s existing history (the prior squash-merged PR, which is out of scope
to rewrite per the no-history-rewrite rule) are left untouched.
