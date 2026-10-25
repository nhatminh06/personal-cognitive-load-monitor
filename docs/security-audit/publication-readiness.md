# Publication readiness gate

Current decision: **BLOCKED BY SECURITY FINDINGS**.

Satisfied locally:

- no confirmed committed secret awaiting rotation;
- production authentication and artifact digest failure paths are tested;
- local service bindings are loopback-only and Redis is authenticated;
- CI permissions/deployment identity are narrowed;
- fixed Python advisory findings were remediated; the no-fix DVC/diskcache cache-write precondition is documented;
- Airflow 3 runs non-root without a Docker socket and dispatches only authenticated, fixed commands;
- MinIO was replaced by a pinned, non-root SeaweedFS S3 endpoint after a hash-verified copy to a new volume;
- GitHub branch and production-environment protections were configured and read back through the API.

Publication follow-up:

1. The hardened feature branch was published as draft PR #6 under a later explicit authorization. GitHub tests, image build/push, and GitGuardian passed.
2. Checksum-verified Gitleaks, Trivy and actionlint plus digest-verified zizmor were executed from a temporary directory. Tracked content has no Gitleaks finding; tracked dependency manifests have no High/Critical result; remaining image/IaC risks are documented.
3. SEC-018 through SEC-021 are remediated. Keep PR #6 in draft because SEC-022 remains open: the refreshed Spark 3.5.5 scan has 126 fixable High/Critical occurrences (107 distinct IDs) across its base OS, Java and Python dependencies.

Required before merge: close SEC-022 by selecting and regression-testing a maintained Spark/Delta/base-image combination. Required before cloud deployment: also close cloud-deferred SEC-011, provision managed secrets/digests, enforce TLS/rate limits/RBAC/image verification, and runtime-test KServe, NetworkPolicy and observability without development credentials. The repository currently has one collaborator, so an independent approval rule cannot be enabled until another qualified reviewer is added.

Latest gate: official Spark 3.5.9 and 4.1.3 images were both rejected after complete exact-digest Trivy scans; neither reduces the fixable High/Critical count to an acceptable level. NV-02 immutable CI publication/deployment and NV-03 SeaweedFS raw-API isolation are implemented, locally validated, and safe to publish independently. SEC-022 still keeps PR #6 in draft.

Git safety: this audit itself performed no Git publication action. A later authorized task created commits, normally pushed the feature branch, merged updated `main` into that branch, and opened draft PR #6. It did not merge the PR, rewrite history, run Terraform apply, provision cloud resources or deploy remotely.
