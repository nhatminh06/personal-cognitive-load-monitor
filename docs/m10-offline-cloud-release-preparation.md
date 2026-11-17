# M10 offline cloud-release preparation assessment

**Baseline:** `b7f3ddef1d30eb52e80887d27445c5724a198ce3` on
`feat/m10-cloud-release-prep`, reviewed 2026-11-17 America/Chicago. M10 is an
offline preparation milestone, not cloud-deployment approval.

## Gate decisions

| Gate | Status | Decision |
|---|---|---|
| Sanitized publication boundary | `PASS_OFFLINE` | PR #50 remains the baseline; no excluded evidence was restored. |
| Ordinary CI | `PASS_OFFLINE` | Read-only tests, coverage, Ruff, and secret scanning only. |
| Manual source qualification | `PASS_OFFLINE` | Exact-commit and acknowledgement bound; read-only permissions; no OIDC, package write, publication, or deployment. |
| Release identity policy | `PASS_OFFLINE` | Fail-closed validation covers authorization, model approval, digests, image identity, SBOM/provenance identity, and exact Trivy reports. |
| Deployment-runner image | `BLOCKED` | Historical candidate has 13 HIGH findings. No exact rebuilt image with zero HIGH/CRITICAL findings exists. |
| GKE Gateway replacement | `NEEDS_RUNTIME` | ingress-nginx is disabled. Secure Gateway, TLS, IAP, Cloud Armor rate limits, health checks, and NetworkPolicy behavior require an authorized disposable cluster. |
| Kubernetes/controller compatibility | `NEEDS_RUNTIME` | Version requirements were checked in official documentation but not reconciled in a cluster. |
| Terraform | `PASS_OFFLINE` | Static controls and an explicit owner gate only; provider-backed plan and cloud APIs remain blocked. |
| Image build, SBOM, provenance, signature, exact-image scan | `NOT_RUN` | No approved replacement runner toolchain or image identity exists. |
| M12 GCP release | `NEEDS_OWNER_APPROVAL` | Billing, plan, IAM, registry, DNS/TLS, secrets, publication, and cluster operations remain prohibited. |

There is no overall `PASS`. Offline controls pass only where stated;
deployment remains **NO-GO**.

## M10 file inventory

- `.github/workflows/release-qualification.yaml`
- `README.md`
- `deploy/gke/runners/README.md`
- `docs/cloud-deployment.md`
- `docs/m10-offline-cloud-release-preparation.md`
- `docs/module3/gke-gcs-readiness.md`
- `helm/cognitive-load-monitor/values.gke.yaml`
- `helm/cognitive-load-monitor/values.module1-knative.yaml`
- `infra/terraform/gke/variables.tf`
- `scripts/validate_release_qualification.py`
- `src/tests/test_gke_cloud_readiness.py`
- `src/tests/test_kserve_manifests.py`
- `src/tests/test_m10_release_security.py`

## Component inventory

| Component | Classification | Boundary |
|---|---|---|
| Ordinary CI | Implemented and validated offline | Read-only; cannot publish or deploy. |
| Manual source qualification | Implemented and validated offline | Protected environment required; still has no privileged permission. |
| GKE Terraform | Implemented but runtime-unverified | Private nodes, control-plane allowlist, WIF, private GAR/GCS, Secret Manager metadata, logs, deletion protection, and budget alerts. No plan/apply. |
| Helm and KServe Standard resources | Implemented but runtime-unverified | Digest/model gates render offline; GKE external ingress is disabled. |
| Knative Serving/Eventing 1.23 | Implemented but runtime-unverified | No controller/CRD reconciliation evidence for this commit. |
| KFP 2.17 | Implemented but runtime-unverified | Historical local evidence only; mutable upstream `master` renders are unacceptable for cloud use. |
| MLflow SQLite/GCS design | Implemented but runtime-unverified | Private, one replica/worker, bounded PVC; not HA or production-ready. |
| Packaging runner | Implemented but runtime-unverified | Non-root and no Docker socket; exact current image scan is absent. |
| Deployment runner | Missing and blocked | No Dockerfile is accepted until a zero-HIGH/CRITICAL toolchain is proven. |
| ingress-nginx | Intentionally out of scope | Retired and disabled for GKE. |
| SEC-022 Spark | Intentionally out of scope | Local-development exception only; absent from cloud and release paths. |

`SET_*` values, zero digests, example project/billing inputs, and historical
deployment instructions are not release inputs. Historical reports remain
evidence only for their named commits.

## Deployment-runner remediation

The mandatory policy is unchanged: any unsuppressed HIGH or CRITICAL result is
a blocker. No ignore file, exception, `--ignore-unfixed`, or severity reduction
is accepted.

Official release metadata checked on 2026-11-17:

| Tool | Observed official release | Decision |
|---|---|---|
| Actions Runner | 2.338.2 remains current | `BLOCKED`: derived image not rebuilt/scanned. |
| Cosign | 3.1.4 remains current | `BLOCKED`: historical Go-runtime findings lack a newer official artifact. |
| Helm | 3.22.1 is current Helm 3; Helm 4.3.2 also exists | `BLOCKED`: do not cross a major version without compatibility qualification. |
| kubectl | 1.35.10 exists for the planned minor | `BLOCKED`: checksum/provenance and exact-image scan not performed. |
| Trivy | 0.76.2 exists | `BLOCKED`: a newer version does not prove the advisory is fixed. |

The historical 13-HIGH matrix remains in
`deploy/gke/runners/README.md`. A deployment-runner Dockerfile is deliberately
not added because unresolved artifacts would create a misleading runnable path.
M11 must checksum-verify official artifacts, build offline, record the OCI
manifest/config identity, generate SBOM/provenance, and scan the exact final
image with zero HIGH/CRITICAL findings.

No container image was scanned in M10, so there is no image digest to record.
The exact scanned configuration roots were `infra/terraform/gke`,
`helm/cognitive-load-monitor`, `deploy/gke`, and `deploy/knative`, using Trivy
check bundle digest
`sha256:0491169789b867ae5a7353381220c1d4d97b3a0d6d9dfd84a25d06f0ba68aa93`.

## Kubernetes compatibility and Gateway decision

Official facts reviewed:

- Kubernetes retired ingress-nginx in March 2026 and states that it receives no
  further security updates.
- KServe 0.20 requires Kubernetes 1.32+, recommends Gateway API, and supports
  Standard mode.
- Knative 1.23 states Kubernetes 1.34 as its minimum.
- GKE documents Gateway TLS, Cloud Armor, IAP, and authorization as separate
  controls; Gateway creation does not reproduce ingress annotations.

| Component | Planned line | Offline result | Runtime requirement |
|---|---|---|---|
| GKE/Kubernetes | Regular 1.35 | `NEEDS_RUNTIME` | Confirm exact regional patch in both zones. |
| KServe | 0.20 Standard | `PASS_OFFLINE` minimum-version check | Reconcile CRDs/controller and predictor. |
| Knative Serving/Eventing | 1.23 | `PASS_OFFLINE` minimum-version check | Reconcile immutable controllers, CRDs, and delivery. |
| KFP | 2.17.x | `BLOCKED` | Resolve every `master` image and qualify the Kubernetes line. |
| cert-manager | 1.18.2 plan | `NEEDS_RUNTIME` | Verify controller/CRD ownership and certificates. |
| ingress-nginx | retired | `FAIL`, disabled | Must not be installed. |
| GKE Gateway API | exact class unresolved | `NEEDS_RUNTIME` | Select scope/class, certificate map, IAP, Cloud Armor policy, static IP, and DNS. |

GKE values now render no external Ingress and the Service remains `ClusterIP`,
so configuration fails closed. M11 may add a Gateway/HTTPRoute only after it can
test HTTPS and redirect behavior, Certificate Manager ownership, IAP,
Cloud Armor rate limiting, API-only route binding, health checks, default-deny
interaction, and proof that MLflow, KServe, brokers, sinks, and runners have no
public route.

## Release workflow threat model

The manual workflow accepts a full SHA and exact
`QUALIFY_ONLY_NO_PUBLISH_OR_DEPLOY` acknowledgement. It compares the SHA to the
selected ref before checkout, checks out without credentials, and has only
`contents: read`. It reruns locked tests, coverage, Ruff, and checksum-pinned
Gitleaks. The declared `m10-release-qualification` environment must later be
protected, but the job has no privileged permission even if it is not.

Negative tests reject missing/malformed Trivy reports, every HIGH/CRITICAL
finding (including unfixed), mutable or duplicate image identities, candidate
models, source/model/image/SBOM/provenance mismatches, and missing authorization.
They also ensure qualification has no OIDC, package write, registry login,
signing, Terraform, Helm, or kubectl authority.

Build, model packaging, and deployment require separate least-privilege cloud
identities. A future publication design must revoke tokens, remove ephemeral
runners and registration Secrets, quarantine bad digests, preserve signed
evidence, and identify orphaned resources before completion.

## Terraform readiness

| Control | Status | Remaining prerequisite |
|---|---|---|
| Explicit project/region/two-zone inputs | `PASS_OFFLINE` | Non-placeholder project and owner-reviewed zones. |
| Owner plan/apply gate | `NEEDS_OWNER_APPROVAL` | Kept outside Terraform so emergency destroy/recovery is never blocked by an authorization toggle. |
| Private nodes/control-plane allowlist | `PASS_OFFLINE` | Validate real `/32` paths and private endpoint access. |
| WIF and separate release/deploy identities | `PASS_OFFLINE` | Configure protected environments and verify IAM. |
| Private GAR/GCS and retention | `PASS_OFFLINE` | Bootstrap isolated encrypted remote state with recovery owners. |
| Secret Manager | `PASS_OFFLINE` | Owner creates and rotates the secret version outside Terraform. |
| Audit/metrics/NAT logs | `PASS_OFFLINE` | Runtime retention, sinks, alerts, and access review. |
| Quotas, NetworkPolicy, storage | `PASS_OFFLINE` | Admission, enforcement, PVC reclaim, and teardown exercise. |
| $225 alert/eight-hour trial | `NEEDS_OWNER_APPROVAL` | Planning constraints only; alerts do not cap spend. |
| Teardown/orphan detection | `BLOCKED` | Approved plan inventory, state backup, and DNS/IP/disk/bucket/registry checks. |

Required owner inputs before M12: billing account/project number, project ID,
notification channels, operator/VPN `/32`s, state bucket/CMEK/recovery owners,
protected-environment reviewers, GKE patch, Gateway class/scope, static IP, DNS,
certificate map, Cloud Armor policy, IAP OAuth secret, Secret Manager version,
approved model/package identity, four image digests, and explicit plan/cost
approval.

## Validation record

Validation used Python 3.11.17, Git 2.56.0, uv 0.13.0, Ruff 0.15.17,
Helm 4.3.0, Terraform 1.15.9, Actionlint 1.7.12, Gitleaks 8.30.0, and
Trivy 0.76.2. The Trivy vulnerability DB was dated 2026-10-25 and is stale;
therefore it is configuration evidence only, not current image-vulnerability
evidence.

| Check | Status | Result |
|---|---|---|
| Focused M10 negative tests | `PASS_OFFLINE` | 13 passed; 51 affected M10/GKE/KServe tests passed. |
| Full Python suite / 81% coverage | `PASS_OFFLINE` | 600 passed, 5 warnings; 87.13% coverage. |
| Ruff / Actionlint | `PASS_OFFLINE` | Repository Ruff and both workflows passed. |
| Gitleaks | `PASS_OFFLINE` | Candidate tree and final commit range passed; see final handoff for commit SHA. |
| Helm lint/render | `PASS_OFFLINE` | Chart linted; GKE render had no Ingress/Gateway/HTTPRoute or mutable image. |
| Kubernetes schema | `NOT_RUN` | No verified schema validator or pinned schema bundle was available. |
| Terraform fmt | `PASS_OFFLINE` | Recursive format check passed. |
| Terraform offline init/validate | `NOT_RUN` | Locked Google provider 5.45.2 was not cached; no download was substituted. |
| Trivy configuration | `FAIL` | Two runner `KSV-0014` HIGH findings; other scanned cloud/chart/Knative paths had zero HIGH/CRITICAL. |
| Exact deployment-runner image build/scan | `NOT_RUN` | No approved compatible toolchain; mandatory blocker. |
| Container build | `NOT_RUN` | Docker daemon access was unavailable; no weaker Dockerfile-only claim substituted. |

The available Trivy 0.76.2 configuration scan currently reports two HIGH
`KSV-0014` findings for the release and deploy runner containers because their
root filesystems are writable. The Helm chart, GKE Terraform, and Knative
manifests have zero HIGH/CRITICAL configuration findings. The runner findings
remain `FAIL`: making the root filesystem read-only without a qualified writable
runner layout would break registration/configuration and manufacture a static
pass without runtime evidence.

## M11 and M12 prerequisites

M11 requires an approved disposable-cluster bill of materials, immutable
controller/CRD identities, a zero-HIGH/CRITICAL deployment runner, protected
qualification environment, secure Gateway policy inputs, and an explicit
no-cloud execution plan. It must test admission, reconciliation, TLS/IAP/rate
limits, NetworkPolicy, storage, event delivery, observability, cleanup, and
orphan detection.

M12 requires owner approval for the exact commit, Terraform plan,
project/billing scope, state backend, IAM, registry publication, model approval,
image/signature identities, DNS/TLS, secrets, eight-hour limit, containment,
and teardown. Otherwise status remains `NEEDS_OWNER_APPROVAL` or `BLOCKED`.

## Primary sources

- <https://kubernetes.io/blog/2026/01/29/ingress-nginx-statement/>
- <https://cloud.google.com/kubernetes-engine/docs/how-to/secure-gateway>
- <https://kserve.github.io/website/docs/0.20/admin-guide/kubernetes-deployment>
- <https://knative.dev/blog/releases/announcing-knative-v1-23-release/>
- Official GitHub release pages for `actions/runner`, `sigstore/cosign`,
  `helm/helm`, `kubernetes/kubernetes`, and `aquasecurity/trivy`.
