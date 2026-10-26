# Publication readiness gate

Current decision: **LOCALLY READY FOR RELEASE CHECKS**. SEC-022 is accepted risk for isolated local development only through 2027-01-23; it is not remediated or authorized for production.

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
3. SEC-018 through SEC-021 are remediated. SEC-022 is explicitly accepted for local development only: Spark 3.5.5 has 126 High/Critical occurrences (122 with reported fixes, 4 without, 107 distinct IDs and 5 Critical).

The named repository owner approved the time-limited exception on 2026-10-25 after the offline Ivy, isolation, Spark/Delta/S3A, Trino/dbt and Airflow checks passed. This permits merging completed security improvements only because Spark remains excluded from every production/Kubernetes path; it does not remediate SEC-022. Required before cloud deployment: remediate SEC-022, close cloud-deferred SEC-011, provision managed secrets/digests, enforce TLS/rate limits/RBAC/image verification, and runtime-test KServe, NetworkPolicy and observability without development credentials. The repository currently has one collaborator, so an independent approval rule cannot be enabled until another qualified reviewer is added.

Latest gate: official Spark 3.5.9 has 719 High/Critical occurrences (181 with reported fixes, 538 without); Spark 4.1.3 has 720 (184 with fixes, 536 without). The hardened 3.5.9 experiment has 178 (99 with fixes, 79 without). The non-deployable patched proof has 21 (19 with fixes, 2 without) and failed strict convergence. NV-02 and NV-03 are implemented; SEC-022 is accepted only within the documented local-development boundary.

Git safety: this audit itself performed no Git publication action. A later authorized task created commits, normally pushed the feature branch, merged updated `main` into that branch, and opened draft PR #6. It did not merge the PR, rewrite history, run Terraform apply, provision cloud resources or deploy remotely.
