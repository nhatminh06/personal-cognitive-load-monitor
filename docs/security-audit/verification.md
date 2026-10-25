# Security verification evidence

Verified locally through 2026-10-25:

| Check | Result |
|---|---|
| Pytest + coverage | 73 passed; 88.67% across both application packages; threshold 81% |
| Focused security tests | 48 passed |
| Ruff 0.15.17 | passed for `src scripts` |
| MyPy 2.4.0 | 22 application/job/script modules passed with explicit package bases; missing third-party stubs ignored |
| Bandit 1.8.6 / Python 3.11 | 0 High, 3 Medium false positives, 7 Low contextual alerts; 1,563 LOC |
| pip-audit 2.9.0 | fixed advisories remediated; one no-fix, development-only diskcache advisory remains |
| Targeted secrets/history scan | no high-confidence matches |
| Compose config | Module II all profiles and observability passed |
| Helm | base, local and GKE lint passed; GKE template rendered |
| Terraform | `fmt -check` and provider-backed `validate` passed outside the restricted plugin sandbox; no plan/apply |
| Graphify | code-only update: 598 nodes, 1,055 edges, 37 communities; no import cycle; semantic mode unavailable without an LLM key |
| DVC | all three stages unchanged/cached with isolated writable site cache |
| Notebooks | all four executed; Notebook 3 was rerun successfully after an explicit skops tree-type allowlist |
| Flink Docker/Maven | four JUnit tests passed through pinned Maven container |
| API Docker smoke | image built; health 200, unauthenticated production prediction 401, authorized prediction 200, production docs 404 |
| GitHub branch-head CI | run 40138099121 passed the coverage gate and model-package/Docker-build/GHCR-push jobs |
| GitGuardian | draft PR #6 check passed after the final branch update |
| Gitleaks 8.30.1 | tracked working tree 0; history 3 documented password placeholders, no real secret |
| actionlint 1.7.12 | passed after CI fixes |
| zizmor 1.31.1 | offline run passed after CI fixes; online audits unavailable |
| Trivy 0.76.1 tracked filesystem | 0 High/Critical dependencies and 0 secrets; only accepted local MinIO-root High remains after GKE/container fixes |
| Trivy API image | exact image `sha256:4775c3…`: 0 fixable High/Critical findings |
| Trivy Flink image | after Jackson 2.18.11 update: 0 Critical, 0 High |
| Trivy Airflow image | Airflow 3.3.2 exact image `sha256:6be8cf…`: 0 fixable High/Critical findings |
| Trivy dbt image | exact image `sha256:989463…`: 0 fixable High/Critical findings |
| Trivy SeaweedFS image | 4.50 exact image `sha256:89fa46…`: 0 fixable High/Critical findings |
| Trivy Spark image | 122 fixable High/Critical occurrences, 103 distinct IDs; SEC-022 blocks merge |
| UI/UX Pro Max dependency review | package-lock-only npm audit for pinned 2.15.0: 0 advisories; package not installed/executed |
| GitHub governance | strict required checks, PR gate, admin enforcement, stale-review dismissal, conversation resolution and protected-only production deployment read back; sole collaborator prevents independent approval |

Not yet verified in this audit: live Kubernetes/KServe/GCP controls, external IAM, ingress rate limiting, TLS, and production secret rotation. Host Maven was missing; Flink Java tests ran through a pinned Maven container. Spark's direct packaged-dependency scan is a known failing result, not an unavailable result.

No destructive/flood/fuzz test was run. Services were not started concurrently.

The manual Kubernetes/Helm deployment job was intentionally skipped: it is restricted to an explicit `workflow_dispatch` on `main`, and remote deployment was outside the authorization for this audit and publication pass.

Final gate commands (binaries were extracted under a temporary directory):

```text
gitleaks dir <tracked-files-snapshot> --redact --report-format json
gitleaks git . --redact --report-format json
trivy fs --scanners vuln,misconfig,secret --severity HIGH,CRITICAL <tracked-files-snapshot>
trivy config --severity HIGH,CRITICAL .
trivy image --scanners vuln --severity HIGH,CRITICAL <local-image>
actionlint -no-color
zizmor --format plain .
pytest src/tests --cov=src/preprocessing_api --cov=src/cogniflow_data --cov-fail-under=81
ruff check src scripts
mypy --explicit-package-bases --ignore-missing-imports src/preprocessing_api src/cogniflow_data
dvc repro && dvc status
terraform -chdir=infra/terraform/gke fmt -check
terraform -chdir=infra/terraform/gke validate
```
