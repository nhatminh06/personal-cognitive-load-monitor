# Security verification evidence

Verified locally on 2026-10-24:

| Check | Result |
|---|---|
| Pytest + coverage | 69 passed; 90.12%; threshold 81% |
| Focused security tests | 48 passed |
| Ruff 0.15.17 | passed for `src scripts` |
| MyPy 2.4.0 | 14 application modules passed with explicit package bases; missing third-party stubs ignored |
| Bandit 1.8.6 / Python 3.11 | 0 High, 3 Medium false positives, 7 Low contextual alerts; 1,563 LOC |
| pip-audit 2.9.0 | fixed advisories remediated; one no-fix, development-only diskcache advisory remains |
| Targeted secrets/history scan | no high-confidence matches |
| Compose config | Module II all profiles and observability passed |
| Helm | base, local and GKE lint passed; GKE template rendered |
| Terraform | `fmt -check` passed; `validate` unavailable because cached Google provider failed startup |
| Graphify | 542-node graph queried; boundary hubs and paths reported |
| DVC | all three stages unchanged/cached with isolated writable site cache |
| Notebooks | all four executed; Notebook 3 was rerun successfully after an explicit skops tree-type allowlist |
| Flink Docker/Maven | build-stage image produced; Maven/JUnit exit 0 |
| API Docker smoke | image built; health 200, unauthenticated production prediction 401, authorized prediction 200, production docs 404 |

Not yet verified in this audit: Trivy/container CVEs, Gitleaks, actionlint/zizmor, live Kubernetes/KServe/GCP controls, external IAM/environment protection, rate limiting, TLS, and production secret rotation. Host Maven was missing; Flink Java tests ran through the Docker build path.

No destructive/flood/fuzz test was run. Services were not started concurrently.
