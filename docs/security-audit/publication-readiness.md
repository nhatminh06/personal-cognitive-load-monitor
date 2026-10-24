# Publication readiness gate

Current decision: **BLOCKED BY SECURITY FINDINGS**.

Satisfied locally:

- no confirmed committed secret awaiting rotation;
- production authentication and artifact digest failure paths are tested;
- local service bindings are loopback-only and Redis is authenticated;
- CI permissions/deployment identity are narrowed;
- fixed Python advisory findings were remediated; the no-fix DVC/diskcache cache-write precondition is documented;
- Airflow socket authority is isolated and accurately documented.

Publication follow-up:

1. The hardened feature branch was published as draft PR #6 under a later explicit authorization. GitHub tests, image build/push, and GitGuardian passed.
2. Checksum-verified Gitleaks, Trivy and actionlint plus digest-verified zizmor were executed from a temporary directory. Tracked content has no Gitleaks finding; tracked dependency manifests have no High/Critical result; remaining image/IaC risks are documented.
3. Keep PR #6 in draft until SEC-018 and SEC-019 are remediated and the upgraded Airflow DAG/MinIO data paths pass runtime regression. GitHub API checks also confirmed SEC-021: `main` is unprotected and `production` has no approvers or deployment policy.

Required before merge: close SEC-018 and SEC-019. Required before cloud deployment: also close SEC-011 and SEC-021, provision managed secrets/digests, enforce TLS/rate limits/RBAC/image verification, and runtime-test KServe, NetworkPolicy and observability without using development Compose credentials.

Git safety: this audit itself performed no Git publication action. A later authorized task created commits, normally pushed the feature branch, merged updated `main` into that branch, and opened draft PR #6. It did not merge the PR, rewrite history, run Terraform apply, provision cloud resources or deploy remotely.
