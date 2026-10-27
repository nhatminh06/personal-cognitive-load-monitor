# CI/CD

Push/PR runs the test job with frozen dependencies, Ruff, Pytest and a strict
81% threshold. A trusted push to `main` automatically runs `build` only after
tests pass. That educational job starts an ephemeral MLflow registry, trains and
registers a model, resolves an exact numeric version, downloads it again, and
publishes a commit-tagged GHCR image. It is not the approved production path.

The protected release workflow is a separate manual job. It packages only an
independently approved exact MLflow name/version/artifact digest, builds four
Artifact Registry images, records SBOM/provenance, resolves repository digests,
signs/verifies them with Cosign and scans those exact digests with Trivy. It
never deploys.

Deployment is manual-only. The existing `production` job preserves KServe
Standard mode for Module III. `deploy-module1.yaml` is separately protected by
the `module1-production` environment and selects the Knative overlay. Both are
main-only, run on the protected deployment runner, use GitHub OIDC and accept
immutable image/model identities. Forked PRs cannot deploy. No permanent GCP
service-account key is created or consumed.

Remote prerequisites still pending are environment reviewers, runner
provisioning, environment secrets/variables, branch protection and the exact
KServe/Knative compatibility approval. No release or deployment workflow was
dispatched during source preparation.
