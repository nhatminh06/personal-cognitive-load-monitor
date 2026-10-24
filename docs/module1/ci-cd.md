# CI/CD

Push/PR runs the test job with frozen dependencies, Ruff, Pytest and a strict 81% threshold. Build depends on test and uses a commit-derived image tag. Deploy is limited to `workflow_dispatch` and the protected `production` environment. It was not triggered.

Future deployment must provide GCP Workload Identity values, an immutable image tag, exact model storage/version, a real hostname and an externally created auth Secret. Forked PRs do not deploy. GCP remains deliberately unconfigured.
