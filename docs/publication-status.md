# Publication candidate status

This branch is a local sanitized candidate based directly on verified public `main` commit `7490eea52e2e858e13f77da86412a1ff5de6e1e8`.

## Scope

- Original application source, tests, local demo paths, deployment configuration, and generated dependency lock metadata are retained.
- Raw Track B evidence, generated notebooks/reports, copied upstream release material, and manual cloud/image publication workflows are excluded.
- Ordinary CI runs tests, coverage, Ruff, synthetic secret-scanner controls, candidate-tree scanning, and event commit-range scanning. It has read-only repository permissions and no publication or cloud job.
- Kubernetes and cloud configuration is available for offline review. This candidate has not run on Kubernetes or GCP.

## Exact candidate validation

The final pre-commit working tree passed these local checks on November 16, 2026 (America/Chicago):

| Check | Result |
|---|---|
| Full Python suite | 586 passed, 5 warnings, 3 subtests passed in 42.50s |
| CI coverage command | 586 passed, 5 warnings, 3 subtests; 87.01% across the configured packages; 81% gate passed |
| Ruff | PASS for `src` and `scripts` |
| Actionlint | PASS for the sole ordinary CI workflow |
| Synthetic API demo | Authenticated `MEDIUM` / `demo_rule`; missing key returned HTTP 401 |
| Secret scanner controls | 34 focused tests and 3 subtests passed; candidate-tree Gitleaks scan found zero findings |
| Dependency lock | `uv lock --check --offline` PASS |
| Package metadata | Source distribution and wheel built locally; both included `LICENSE` |
| Helm | Lint PASS; two default renders were byte-identical |
| Kubernetes schema | Six default rendered objects passed the pinned Kubernetes OpenAPI structural schemas; admission and reconciliation remain unverified |
| Terraform | Recursive format check and offline provider-backed GKE validation PASS; no plan or apply |

Tools: Python 3.11.17, Git 2.56.0, uv 0.13.0, Ruff 0.15.17, Helm 3.22.1, Terraform 1.15.9, and the locally qualified Gitleaks binary with SHA-256 `8b21e851dade39b96e3c59058248c025006d0127117be99a2153cca0212d2c1c`.

Hosted GitHub Actions, required-check enforcement, Kubernetes runtime, cloud deployment, container publication, and exact-image scanning remain `NOT_RUN` or `NOT_VERIFIED`.

## Publication gate

Candidate status is `CANDIDATE_ENGINEERING_PASS` and `READY_FOR_OWNER_REVIEW`. Publication remains `PUBLICATION_BLOCKED` until the owner explicitly authorizes the exact candidate commit and the existing destination repository. This document is not publication approval.
