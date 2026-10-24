# CI/CD security

The workflow has read-only global permissions. Package write exists only in the build job; OIDC write exists only in the deploy job. Pull requests test but do not build/push. Deployment requires `workflow_dispatch`, the `main` ref and the protected `production` environment. Namespace and image-tag input formats are validated before shell use.

The GCP WIF provider condition binds repository and `refs/heads/main`. Unused Artifact Registry writer and model-bucket object-admin grants were removed. The workflow publishes the commit-derived image tag only; no mutable `latest` tag or secret build argument remains.

All workflow actions are pinned to immutable commits resolved from the existing official major-version tags (SEC-012). Enable branch protection, required reviews, environment approvers and artifact attestations on GitHub. None of those remote settings were changed here.
