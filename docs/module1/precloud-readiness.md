# Module I pre-cloud readiness

**Decision date:** 2026-10-27 (America/Chicago)  
**Reviewed source:** PR #22 head `9dd2409573d7f63fafb2f74f02df6725b46c6305`
plus the focused dedicated-kubeconfig correction recorded with this report
**Decision:** **NO-GO for cloud deployment.** Offline preparation is complete
enough to request a separately authorized disposable qualification, but the
compatibility matrix remains `BLOCKED` and no Kubernetes or GCP runtime proof
was produced in this pass.

This report is the authoritative Module I pre-cloud status. Source, prior local
runtime evidence, current offline checks, future isolated-kind evidence and
future GKE evidence are deliberately separate.

## Current model-selection correction

The model-quality and authorization policy is now documented in
[`model-selection-policy.md`](model-selection-policy.md). The current synthetic
random forest is not selected or approved: its recorded accuracy/macro-F1
(`0.88`/`0.8678356121965144`) are lower than the directly comparable logistic
candidate (`0.96`/`0.9514687100893998`), and the pipeline has no separate
validation split or predeclared selection rule. Mutable MLflow approval tags and
a caller-supplied actor are not independent authorization. A signed approval
predicate and signed model/package-to-image binding remain unimplemented.

PR #30 is merged, but its local kind evidence decision still requires an
independent reviewer. Model selection, scientific validation, release
authorization, kind acceptance, GKE compatibility, and compatibility-matrix
promotion remain separate gates. Nothing in this correction changes the
**NO-GO** cloud decision below.

## Source and pull-request dependency

The branch order is:

1. `main` at `3595356`;
2. draft PR #21, `feature/cogniflow-module1-compatibility` at
   `059b49b0badaaef9795a69c4613d994ed4df2554`, based on `main`;
3. draft PR #22, `feature/cogniflow-module1-isolated-qualification` at reviewed
   head `9dd2409573d7f63fafb2f74f02df6725b46c6305`, based on PR #21.

GitHub reported both drafts open, mergeable and `CLEAN` on 2026-10-27. PR #21's
test and GitGuardian checks passed; its build and deploy jobs were skipped. PR
#22's test and GitGuardian checks passed; its build and deploy jobs were also
skipped. PR #22's hosted test job reported 387 passed, 4 warnings and 88.89%
coverage. The combined `main...PR #22` diff is Module I-scoped except for the
required README and submission-status references.

Do not merge or rebase automatically. After review:

```bash
gh pr merge 21 --squash   # human action only
git fetch origin
git switch feature/cogniflow-module1-isolated-qualification
git rebase origin/main
git push --force-with-lease
gh pr edit 22 --base main
```

Resolve conflicts by retaining the fail-closed compatibility gate and Module
III's default `Standard` mode. Re-run all checks after the rebase, then merge PR
#22 only by an authorized reviewer.

## Requirements and evidence

`PASS_OFFLINE` means the current source or an offline render/check directly
proved the requirement. Prior runtime claims remain labeled as prior evidence,
not proof produced by this pass.

| Requirement | Status | Evidence and remaining work |
|---|---|---|
| Pytest and coverage strictly above 80% | PASS_OFFLINE | PR #22 hosted CI: 387 passed, 88.89%; workflow enforces `--cov-fail-under=81`. Re-run on the final rebased commit. |
| CI test before build | PASS_OFFLINE | `build.needs: test`; publication is main-push only. Draft-PR build was skipped. |
| Manual protected deployment | NEEDS_HUMAN_APPROVAL | Dispatch-only, main-only, OIDC and `module1-production` environment are source-defined. Reviewers, runner, variables and secrets require owner verification; no dispatch occurred. |
| FastAPI preprocessing/postprocessing | PASS_OFFLINE | Bounded schemas, six-feature transformation, explicit provenance and failure mapping are tested. `demo_rule`, `local_model` and `kserve` are explicit modes and do not silently fall back. |
| API HPA | PASS_OFFLINE | `autoscaling/v2`, 2–5 replicas, CPU target, bounded behavior and resource requests render. Runtime 2→N→2 remains `NEEDS_GKE_RUNTIME`. |
| KServe Knative/KPA contract | PASS_KIND_RUNTIME_PENDING_REVIEW | Module I overlay renders Knative, KPA concurrency, min 0/max 3/target 1 and bounded timeouts. Preserved kind evidence records 2→0→2; independent review remains pending. |
| Module III KServe | PASS_OFFLINE | Default and GKE render remain `Standard` with a three-second client timeout. |
| NGINX authentication and TLS | PASS_OFFLINE | Production render refuses missing TLS or auth Secret and remains digest-only. Certificate, 401/200 and backend-bypass evidence need `NEEDS_GKE_RUNTIME`. |
| Prometheus and Grafana | PASS_OFFLINE | Metrics endpoint, ServiceMonitor and provisioned dashboard exist; prior local runtime evidence is documented. Hosted scrape/dashboard need `NEEDS_GKE_RUNTIME`. |
| Loki structured logging | PASS_OFFLINE | Structured/redacted logging and local Loki configuration exist; hosted correlation needs `NEEDS_GKE_RUNTIME`. |
| OpenTelemetry and Tempo | PASS_OFFLINE | OTLP configuration and instrumentation exist; hosted trace correlation needs `NEEDS_GKE_RUNTIME`. |
| Evidently drift | PASS_OFFLINE | DVC stage and checked-in report path exist. Final reference/current metadata replay is `NOT_RUN`. |
| DVC reproducibility | BLOCKED | The ignored working manifest differs from the cached/locked artifact only in `git_revision` (`5237d674…` → `4b9ccec5…`). Dataset, feature and label bytes match their locked hashes. This deterministic shared Module III lineage drift does not corrupt Module I data, but must not be accepted here. |
| MLflow exact model retrieval | PASS_OFFLINE | Packaging requires exact registered name, version and artifact-tree digest and rejects a candidate. GCS/registry round trip needs `NEEDS_GKE_RUNTIME`. |
| Python implementation | PASS_OFFLINE | API, preprocessing, model client, custom KServe runtime, training and evidence guards are Python and pass Ruff, MyPy and Pytest. |
| Four notebooks | PASS_OFFLINE | Four valid nbformat-4 notebooks are present and prior execution is documented. Clean-environment replay is `NOT_RUN`. |
| Helm and Terraform source | PASS_OFFLINE | Standard and Knative Helm lint/render passed. GKE Terraform formatting and provider-backed `terraform validate` passed in a disposable backend-free copy using locked Google provider 5.45.2; no credentials, plan or state were used. |
| Actual cloud Kubernetes deployment | BLOCKED | GKE Terraform and Helm source exist, but no project, spending, plan, provisioning or deployment is authorized and no GKE runtime evidence exists. |
| GitHub PR with code and documentation | PASS_OFFLINE | Draft PRs #21 and #22 are open, clean and mergeable; both require human review and integration. |
| README/submission/evidence guides | PASS_OFFLINE | README, rubric, acceptance guide, evidence schema, submission checklist and this report are present. Final cloud evidence remains intentionally incomplete. |
| Optional demonstration video | NOT_RUN | No video was recorded; this optional item cannot substitute for mandatory runtime evidence. |

## KServe and Knative qualification review

The only candidate under consideration is immutable Kubeflow Community
Distribution commit `f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0`:

- KServe 0.21.0;
- Knative Serving 1.23.0;
- Istio 1.31.3;
- cert-manager 1.21.2;
- exact disposable Kubernetes 1.34.11, with `gke_accepted: false`.

The prepared inventory requires 15 workloads and 38 CRDs. It intentionally omits
the KServe UI, local-model node agent and disabled kernel-cache node agent. The latter's
published `v0.21.0` image is inaccessible and the feature is unnecessary for CogniFlow.
The installer preserves the raw render, pins all ten other mutable source tags to reviewed
linux/amd64 manifest digests, records the exact omission, and applies only the prepared
render. Istio CNI retains host access to
`/opt/cni/bin`, `/proc`, `/etc/cni/net.d`, `/var/run/istio-cni` and
`/var/run/netns`; that cluster-level privilege must be independently accepted.
The installer records exact rendered manifests and resource identities before
cluster creation. Runtime capture then verifies those identities, readiness,
live image IDs and effective autoscaler/timeouts. Missing or unverifiable data
fails closed, and only a human reviewer can populate `approved_inventory` or
change `BLOCKED`.

The qualification scripts require `--execute`, a new absolute evidence path
outside the repository, a nonexistent cluster/context, exact context binding,
at least 10 GiB free host and Docker memory, 4 CPUs and 30 GiB free disk. Their
expected peak is 12 GiB, so a 16 GiB laptop has only a 4 GiB nominal margin.
The installer and qualifier use only a mode-0600 kubeconfig inside that external
evidence directory; they do not add the disposable context to the user's default
kubeconfig.
At final review time only 7.49 GiB was available, so installation is currently blocked
even with authorization. Close other workloads and stop if preflight fails. Installation, qualification
and deletion each require separate authorization; the documentation records a cleanup
command, but no script invokes it automatically.
Use a disposable linux/amd64 host with at least 16 GiB actually available to Docker,
at least 4 CPUs, 30 GiB free disk, and a version-recorded Docker Buildx installation.
The reviewed host lacks Buildx, so it cannot execute the documented immutable local-image
packet even after memory is freed.

The acceptance contract is strict HTTP 200 prediction and metadata over the
cluster-local route, positive Ready replicas→0→positive, a single non-retried cold request
with a 35-second curl deadline and 40-second outer bound, and preserved PASS or
FAIL evidence. Negative mutations cover version, digest, CRD, rendered source,
autoscaler, route and acceptance drift. No installer or qualification command
was run here.

## Security and supply-chain disposition

The qualification client has no RoleBinding, does not mount its service-account
token, uses a digest-pinned curl image, Restricted Pod Security settings,
bounded resources and bounded `/tmp`. The production render now gives the API
pod RuntimeDefault seccomp and bounds the predictor `/tmp` at 64 MiB. API and
predictor Services remain internal; production ingress requires TLS and Basic
Auth; model and API images must be immutable digests.

The seven upstream allow-all Istio policies are **not approved** merely because
they are inventoried:

| Policy | Scope found in pinned render | Disposition |
|---|---|---|
| `istio-system/cluster-local-gateway` | all traffic to the exact cluster-local gateway selector | Needed for internal Knative routing under namespace default-deny; broad at the gateway and requires runtime route/ingress review plus human acceptance. |
| `istio-system/istio-ingressgateway` | all traffic to the exact ingress-gateway selector | Required by the upstream gateway base, but no public qualification route is created. Never copy to predictor namespace; human acceptance required. |
| `knative-serving/activator-service` | all traffic to activator pods | Activator must receive cold-start traffic; exact source/port restriction is not validated upstream and requires runtime evidence/human acceptance. |
| `knative-serving/autoscaler` | all traffic to autoscaler pods | Supports KPA metrics/control traffic under default-deny; retain only with namespace isolation and human acceptance. |
| `knative-serving/controller` | all traffic to controller pods | Supports controller webhook/control communication under default-deny; retain only with RBAC/network evidence and human acceptance. |
| `knative-serving/istio-webhook` | all traffic to net-istio webhook pods | Admission/control traffic is required, but the source policy is broader than proven necessary; human acceptance required. |
| `knative-serving/webhook` | all traffic to serving webhook pods | Admission/control traffic is required, but the source policy is broader than proven necessary; human acceptance required. |

Any additional allow-all policy, especially in the qualification or predictor
namespace, fails inventory verification. The upstream test-only permissive
predictor policy, default credentials and sample configuration are not reused.

Security findings and scan state:

| Exposure | Severity/state | Affected component | Required remediation/disposition |
|---|---|---|---|
| Overly permissive Istio permissions can enable Kubeflow token theft (`GHSA-v824-8gxh-pgjw`) | High upstream advisory; constrained but not independently closed | Kubeflow profile/editor roles and Istio routing permissions | Minimal qualification omits profiles/editor bindings and grants its model SA no RoleBinding. Verify captured `auth can-i` output; independent reviewer must accept the boundary. |
| Mutable source image tags | Source corrected; runtime verification pending | Ten required KServe, Istio and cert-manager image references | linux/amd64 manifest digests were resolved from public registries and are substituted before apply. Runtime `imageID` comparison remains mandatory. The inaccessible optional kernel agent is omitted. |
| Exact image CVEs/SBOMs unavailable | `NOT_RUN` | all 15 required control-plane workloads and the two CogniFlow release images | Trivy/OSV/SBOM/signature evidence is mandatory before approval. No exception or downgrade is recorded. |
| Istio CNI host paths | privileged host boundary | `kube-system/istio-cni-node` | Accept only for the exact disposable/GKE topology after node and RBAC review. |
| Tag-based build stages | reproducibility risk | `python:3.11-slim`, `ghcr.io/astral-sh/uv:0.10.0` | Release provenance records resolved bases, but a human should approve digest pinning before production release. |

Istio 1.31.3 contains the fixes announced for 1.31.0–1.31.2, including the
October 2026 security updates. cert-manager 1.21 lists Kubernetes 1.33–1.36 as
supported/tested. Those component facts do not establish integration or GKE
compatibility. GKE qualification remains separate.

Unavailable tools were not credited: Docker Buildx, ShellCheck, actionlint, Gitleaks, Bandit,
pip-audit, Checkov, Trivy, Syft, Grype and Cosign were not installed. GitGuardian
passed on both draft PRs, but it is not a substitute for the missing scans.

## Bounded GKE cost estimate

The checked-in topology is a regional `us-central1` cluster with one
`e2-standard-4` node in each of two zones. Using current public list prices,
the two nodes are about `$0.2680/hour`, the regional GKE management fee is
`$0.10/hour`, one forwarding rule is `$0.025/hour`, and Cloud NAT for two
instances plus one external IP is about `$0.0078/hour`. That is approximately
`$0.4008/hour`, or `$3.21` for eight hours, before 200 GiB of balanced disks,
artifact/model storage, logging, traffic and taxes. Keep the existing
conservative `$6–$12` eight-hour authorization envelope; a reviewed billing
estimate and budget owner remain mandatory because budget alerts do not cap
spend.

Price basis: [GKE management](https://cloud.google.com/kubernetes-engine/pricing),
[E2 compute](https://cloud.google.com/products/compute/pricing/general-purpose),
[load balancing and Cloud NAT](https://cloud.google.com/vpc/network-pricing),
and [Cloud Logging](https://cloud.google.com/logging). No cloud pricing API,
project, billing account or credentials were accessed.

## Read-only model approval packet

This packet describes a candidate; it does not approve, promote, package or
deploy it.

| Field | Recorded candidate |
|---|---|
| Registered model | `cognitive-load-classifier-phase2` |
| Version | `2` |
| MLflow run | `94253b877a8c4d45a36abba85a25d4bc` (`FINISHED`) |
| Registered artifact-tree SHA-256 | `13137be7ce4c885877d7968afa0177be31cff60a4b2e33707893a7698c3b62ae` |
| Registry source | `models:/m-c1dfec4cea3e4e1b8f71df1365fcfdec` |
| Model artifact SHA-256 | `278e99a3f3f9b1b9bce7aa05b9386c9e33767c2e8d8df5607facea23f7bb2270` (`model.skops`) |
| Dataset SHA-256 | `6679e9edb87451ee968e21c0aef5280226b2cf609554e048ec365378c3aca80f` |
| Training source | `5237d674edf295addeafb7528920d9f41ade05ba`, 108/36/36 chronological split |
| Recorded metrics | validation accuracy/macro-F1 1.0/1.0; test accuracy/macro-F1 1.0/1.0 |
| State | `candidate`; not approved |
| Format | `.skops`; declared trusted type `sklearn.tree._tree.Tree` |
| Feature contract | schema `1.0`, six ordered features |
| Label provenance | `synthetic_proxy`; fidelity to a synthetic rule, not clinical or real-world cognitive validity |

These values were re-read from `mlflow-phase2.db` in SQLite read-only mode and
the artifact-tree digest was recomputed without deserializing the model. The
prompt's expected name `cognitive-load-classifier` does not identify version 2
in this registry and must not be used as an approval substitute.

Approval requires a human record naming the actor, UTC time, exact model name
and version, registry URI/run, artifact-tree digest, model digest, dataset
digest, source commit, feature schema/order, trusted types, evaluation report
and synthetic-proxy limitation. The packaging gate must independently retrieve
that exact version, verify the artifact tree before `.skops` deserialization,
bind the resulting model/package digests to the exact KServe image digest, and
retain the signed image/SBOM/provenance evidence. None of those approval actions
occurred here.

## Offline checks from this pass

Passed:

```text
uv run --offline ruff check src scripts
  All checks passed
uv run --offline mypy ... --ignore-missing-imports
  Success: no issues found in 32 source files
bash -n qualification/module1/*.sh scripts/capture_module1_runtime.sh
jq empty docs/module1/*.json
jq notebook structure checks for notebooks/*.ipynb
helm lint helm/cognitive-load-monitor
helm template (Standard and Module I Knative, synthetic digests)
python scripts/module1_compatibility.py --matrix docs/module1/compatibility-matrix.json
terraform -chdir=infra/terraform/gke fmt -check
```

Other results:

- hosted PR #22 CI after the focused correction: 387 passed, 4 warnings, 88.89% coverage;
- focused read-only sandbox regression: 60 passed in 3.04 seconds;
- final isolated source-review regression: 49 passed in 1.72 seconds;
- the full local suite stalled after 45 tests in the restricted sandbox and was
  stopped; it is `NOT_RUN` to completion, not a pass or product failure;
- `dvc status`: known manifest drift described above;
- isolated `terraform init -backend=false` and `terraform validate` passed using
  the locked Google 5.45.2 provider in a disposable copy; no backend, credentials,
  plan or Terraform state was opened;
- no Kubernetes, Docker build/scan, cloud, model approval, publication,
  benchmark or credential-backed command ran.

## Remaining acceptance and exact authorizations

1. **Human source review:** approve PR #21, integrate it, rebase/retarget PR #22,
   confirm the combined scope and pass final CI.
2. **Disposable installation authorization:** approve the exact pinned commit,
   Kubernetes 1.34.11 node image, 12 GiB expected peak, 30 GiB free disk, new
   external evidence directory and exact cluster/context name.
3. **Disposable qualification authorization:** separately approve building a
   local-only synthetic `.skops` image, loading it into that cluster and running
   the strict acceptance/negative tests. No production credentials or model
   status changes.
4. **Independent evidence decision:** review all renders, 15 workload image IDs,
   38 CRDs, RBAC, seven policies, scans and positive→0→positive evidence. Only that reviewer
   may update the matrix. Keep it `BLOCKED` until then.
5. **Disposable deletion authorization:** separately approve deletion only
   after immutable evidence retention.
6. **Model approval:** separately approve the exact registered candidate packet;
   do not infer approval from registration or qualification artifacts.
7. **Release authorization:** approve exact image digests, signatures, SBOMs,
   provenance, vulnerability dispositions and model-to-image binding. Do not
   publish or sign from this pass.
8. **Cloud authorization:** approve project/billing/budget, backend/state,
   reviewed no-create plan, GKE patch/region, IAM/OIDC, protected environments,
   DNS/TLS/secrets, rollback owner, teardown owner and evidence retention before
   any credential-backed plan, creation or deployment.

## Cloud stop conditions and decision

Stop before mutation if the matrix is not independently qualified; any live
version, digest, CRD, configuration, context, namespace UID, release owner,
revision or manifest identity differs; the model is not explicitly approved;
an image is unsigned/unscanned; TLS, authentication, NetworkPolicy, Pod
Security, IAM, backup, budget or teardown ownership is missing; capacity is
insufficient; or SEC-022's Spark image could reach cloud.

Rollback requires the exact prior Helm revision, prior manifest identity,
immutable images, owner and evidence window. Teardown is a separate reviewed
operation after evidence capture; never destroy automatically on test failure.

**Go/no-go:** offline source preparation is complete with one known DVC lineage
drift and missing external scanners explicitly recorded. A disposable isolated
qualification is source-ready to request under the three separate authorizations
above, but current available RAM is below preflight minimum. Cloud deployment,
protected workflow dispatch, matrix
qualification, model approval and release publication remain blocked.
