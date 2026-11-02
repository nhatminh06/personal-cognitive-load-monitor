# GKE/GCS deployment and final-demo runbook

**Status:** planning and offline validation only, 2026-10-26. Nothing in this runbook has been applied to GCP. Read [the cloud-readiness design](module3/gke-gcs-readiness.md) first.

## 1. Owner approvals and release inputs

Record approvals for project/billing account, `us-central1`, a maximum **$225** project budget alert (alerts do not cap spend), an eight-hour initial lifetime, remote state, IAM, DNS/TLS, image publication and the exact Terraform plan. Model approval is separate and is not granted here.

Required immutable inputs:

- exact GKE version available in both planned zones;
- reviewed add-on manifest/chart digests from the compatibility matrix;
- API, KServe, event consumer and anomaly images in Artifact Registry by registry digest;
- candidate lineage and approved package digests, only if an authorized owner has separately approved a model;
- operator/VPN `/32`, owned hostname, certificate issuer and Secret Manager/Kubernetes secret-sync procedure.
- fixed operator/VPN `/32` for public control-plane access. The in-cluster deployment runner uses the internal control-plane endpoint and does not add its Cloud NAT address to master-authorized networks;
- approved project-scoped budget alerts, an exact KFP/MLflow image digest and a passing two-node resource-budget check.

Stop if GitHub `main` is not branch-protected, environment administrator bypass is enabled, the deployment runner cannot reach the internal endpoint, any image uses a tag without a digest, a signature/scan fails, a manifest renders `:master`, capacity does not fit, the budget is absent, or a Terraform target differs from the approved project.

## 2. State and static preflight

Do not inspect, move or reuse ignored local state. Its recorded `0644` permissions must be remediated by its owner. Bootstrap the dedicated state bucket separately, review its IAM/retention, then copy `infra/terraform/gke/backend.tf.example` to the deliberately untracked `backend.tf` and initialize with migration disabled until approved.

```bash
terraform -chdir=infra/terraform/gke fmt -check -recursive
terraform -chdir=infra/terraform/gke init -backend=false
terraform -chdir=infra/terraform/gke validate
helm lint helm/cognitive-load-monitor
pytest --cov --cov-fail-under=81
ruff check .
mypy src/preprocessing_api src/cogniflow_data src/cogniflow_anomaly src/cogniflow_eventing
```

Compile KFP, parse every Kubernetes YAML, run DVC status, Gitleaks and High/Critical configuration/image scans. These commands are validation, not authority to create cloud resources.

Run `pytest -q src/tests/test_gke_cloud_readiness.py::test_cloud_guardrails_and_two_node_budget_are_enforceable` as the two-node arithmetic gate. Then render all pinned controllers and replace every estimate in `deploy/gke/resource-budget.yaml` with the summed requests. Offline arithmetic cannot prove that GKE's scheduler will accept the topology.

## 3. Reviewed plan (still no apply)

Create an untracked tfvars file from the example. Set the project, two zones in the same region, external operator `/32`, GitHub repository, owner-approved billing account and numeric project number. Terraform intentionally refuses a plan without the budget inputs.

```bash
terraform -chdir=infra/terraform/gke plan -out=PR17-REVIEW-ONLY.tfplan
terraform -chdir=infra/terraform/gke show PR17-REVIEW-ONLY.tfplan
```

Review resource count, region, IAM members, private nodes, authorized networks, retention, `force_destroy=false`, deletion protection and estimated cost. Never commit the plan (it can contain sensitive values). A changed plan invalidates approval.

## 4. Authorized provisioning and cluster gates

Only an authorized operator may apply the exact reviewed plan. Immediately confirm two private nodes, Workload Identity, Dataplane V2, Cloud Logging/Managed Prometheus, only reviewed external operator `/32` control-plane networks, budget alerts and Artifact Registry/GCS public-access prevention. Dataplane V2 already enables policy enforcement; do not add the incompatible GKE `network_policy` switch. A bootstrap cluster administrator substitutes the reviewed project ID and applies `deploy/gke/cogniflow-guardrails.yaml`; the deployment identity then has namespace admin only. Apply the eventing namespace/policy before its workloads.

The public endpoint remains enabled for the external operator. All three deployment workflows set `use_internal_ip: true`, so the in-cluster `cogniflow-gke-deploy` runner reaches the private control-plane CIDR directly. Cloud NAT is only outbound connectivity for private nodes and Pods to GitHub, Google OIDC endpoints and Artifact Registry; its automatically allocated address is not a control-plane allowlist input. The release runner also uses NAT for those HTTPS destinations and reaches MLflow through `mlflow.mlflow.svc.cluster.local` inside the cluster.

Render `deploy/gke/ephemeral-runners.yaml` only after replacing every `SET_*_IMAGE` with a reviewed digest. Create the registration-token Secret separately in the relevant namespace, start one Pod for one authorized job, then delete the Pod and Secret and confirm GitHub removed the ephemeral registration. The private packaging image needs only the pinned runner plus the prerequisites for the SHA-pinned Python and uv setup actions. The deploy image needs the pinned runner, Google Cloud CLI, `kubectl`, Helm, Cosign and Trivy. Neither Pod receives a Kubernetes API service-account token or Docker socket.

### Runner image and bootstrap gate

Read-only registry inspection on 2026-11-01 identified this maintained upstream amd64 runner base:

- runner base: `ghcr.io/actions/actions-runner@sha256:0ce3288e48b012a83685998f683a2ae0cbd284fa722c090dda0af5443215cf30` from the attested multi-platform `2.338.2` index `sha256:759a1d94a15b05941aba5196974ff43fe15b4cbba29b694b35cbc32a1166b232`;

`deploy/gke/runners/Dockerfile.release` derives the private packaging runner from that base, applies a checksum-pinned Ubuntu `libbrotli1` security update, removes its unused container toolchain and privileged group memberships, and preserves UID/GID 1001. Its local Linux/amd64 build passes the mandatory HIGH/CRITICAL Trivy gate. This is not a registry reference: publish through a separately authorized bootstrap path and verify the registry amd64 manifest digest before replacing `SET_RELEASE_RUNNER_IMAGE`. The vulnerable deployment runner remains blocked and `SET_DEPLOY_RUNNER_IMAGE` must remain unresolved.

The protected workflow is split at the network boundary. The restricted `cogniflow-release` Pod performs the solo-owner authorization and reads private MLflow to produce exactly `cognitive_load_model.skops` and `model-package.json`. It computes a package-tree SHA-256 as a job output and uploads only those two files for one day. A GitHub-hosted job downloads the artifact, independently validates its exact file set, model digest, package-tree digest and complete approval/model identity, then builds, scans, signs and verifies the images. The artifact contains no token, credential or MLflow tracking URI. This removes BuildKit from GKE rather than weakening Restricted Pod Security.

Obtain a one-hour repository registration token only immediately before the approved job and stream it directly into the namespaced `github-runner-registration` Secret; do not place it in shell history, a manifest, a command argument or a file. Apply one runner Pod, wait for its readiness marker, then delete the Secret. The startup script unsets `RUNNER_TOKEN` before `run.sh`, preventing job steps from inheriting it. Default labels add `self-hosted`, `Linux` and `X64`; the manifest adds exactly `cogniflow-release` or `cogniflow-gke-deploy`. `--ephemeral` accepts one job, the four-hour Pod deadline bounds abandoned runs, and the operator deletes the completed Pod and confirms the GitHub registration disappeared. A Pod that registers but never accepts a job requires explicit runner removal through GitHub before retrying.

Install pinned cert-manager, ingress-nginx, Knative Serving/Eventing, KServe Standard and standalone KFP in compatibility order. Resolve every deployed image ID and compare it with the evidence ledger. Reject mutable `master`, `latest` or SHA-shaped tags.

Render `deploy/gke/mlflow.yaml` with the project ID, Terraform bucket name and a KFP/MLflow image in exact `repository@sha256:<64 lowercase hex>` form; reject a tag or unresolved placeholder before apply. The single replica keeps registry metadata in SQLite on its PVC and proxies artifacts to GCS through the existing `mlflow/mlflow` Workload Identity. Before training acceptance, record the candidate run's GCS object names and generations from the Terraform bucket, then independently download the registered source through MLflow and compare its artifact-tree SHA-256 with the candidate tag. Proxy-backed registered sources may use `mlflow-artifacts:/`; they are not evidence of a literal `gs://` model-source URI. The protected release runner must execute in-cluster (or use a separately reviewed private connection) so `MLFLOW_TRACKING_URI=http://mlflow.mlflow.svc.cluster.local:5000` resolves; do not expose MLflow publicly. Install External Secrets Operator chart 2.13.0 by reviewed digest. Apply `deploy/gke/external-secret.yaml` before Helm; it can reconcile after Helm creates `cogniflow-api`. Verify only the expected Secret keys, without printing values.

## 5. Candidate training and explicit promotion

Submit one bounded KFP run by immutable component digest. Confirm all six tasks, dataset digest, KFP run ID and MLflow candidate tags. A successful run must remain `candidate`; it must not update an alias/stage used by serving.

Pause for the owner's explicit educational release decision. If and only if the
repository owner acknowledges the exact name, version, run and digest, dispatch
the existing approval/package workflow and record its lineage. This is not an
independent review. Any identity, revision or digest mismatch stops the run.

## 6. Digest-pinned application deployment

An approved operator creates the Secret Manager secret version and the external Kubernetes Secrets without printing values. Render first; the checked-in sentinels must fail closed.

The manual `.github/workflows/release.yaml` jobs use the separately protected
`production-release` environment and do not deploy. After the repository owner
supplies the exact acknowledgment, the in-cluster job records a solo-owner
educational authorization for the exact MLflow name/version/run and artifact-tree
digest, packages that same tuple and transfers the independently hashed two-file
package with one-day retention. The hosted job verifies that package, then uses
the release-only Google service account to build the API, KServe, event-consumer
and anomaly images once, resolves
their Artifact Registry digests, emits BuildKit SBOM/provenance attestations,
and uses Cosign 3.1.4 keyless signing with GitHub OIDC. It verifies each
signature and runs Trivy 0.76.1 against that same digest before retaining the
non-secret evidence. The main-push job in `ci-cd.yaml` remains a GHCR CI build;
it is not a production release.

Provisioning the `cogniflow-release` runner and setting its
`MLFLOW_TRACKING_URI` secret remain owner-controlled pending operations. The hosted
job receives `GCP_RELEASE_WORKLOAD_IDENTITY_PROVIDER`,
`GCP_RELEASE_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`, and `GAR_LOCATION` through the
protected environment. The Terraform
OIDC bindings separate the `production-release` publisher from the `production`
deployer and bind each impersonation grant to its environment. On the dedicated
deploy runner, `scripts/verify_cloud_release.sh` re-verifies the release identity
and runs Trivy against the exact digests before Helm.

The existing protected `deploy` job in `.github/workflows/ci-cd.yaml` installs
only the Helm API/KServe chart and verifies only those two image digests. It
does **not** install the rendered logging, dead-letter, anomaly-detector or
alert-sink workloads and must not be cited as four-image deployment evidence.

```bash
helm template cogniflow helm/cognitive-load-monitor \
  --namespace cogniflow -f helm/cognitive-load-monitor/values.gke.yaml \
  --set-string image.digest=sha256:<API_DIGEST> \
  --set-string kserve.image.digest=sha256:<KSERVE_DIGEST> \
  --set-string kserve.name=<APPROVED_NAME> \
  --set-string config.modelName=<APPROVED_NAME> \
  --set-string config.modelVersion=<APPROVED_VERSION> \
  --set-string config.modelSha256=<MODEL_SHA256> \
  --set-string config.modelArtifactSha256=<ARTIFACT_SHA256> \
  --set-string config.modelDatasetSha256=<DATASET_SHA256>
```

Inspect TLS, ServiceAccounts, requests/limits and NetworkPolicies, then use the same exact overrides for `helm upgrade --install`. Deploy the digest-pinned logging consumer, anomaly detector and sink with bounded PVCs. SEC-022 Spark must not appear in any GKE namespace.

Never apply the checked-in Knative workload YAML directly in GKE: those files
intentionally contain local `:dev` images and `imagePullPolicy: Never`.
`scripts/render_production_knative.py` is the fail-closed production path. It
accepts only the two released Artifact Registry digest references, replaces all
four logging/dead-letter/detector/sink container occurrences, and fails if any
mutable or development image remains. Apply its reviewed output only from the
separate manual `.github/workflows/deploy-knative.yaml` action. That workflow is
main-only, uses the separately protected `production-knative` environment and
the OIDC deployer identity, re-verifies all four released image digests, checks
namespace-local authorization and restricted Pod Security admission, then
applies the network policy, Broker, rendered workloads and Triggers. It neither
builds nor publishes images. Before its first authorized run, a bootstrap
administrator must create/label the namespace and apply
`deploy/gke/eventing-deployer-rbac.yaml` with the reviewed project substitution;
the workflow deliberately cannot grant itself access.

## 7. Final demo acceptance

Capture timestamps and exact digests for every check:

- TLS endpoint rejects unauthenticated traffic and serves authenticated `/health`, `/model-info` and `/predict` without exposing secrets;
- FastAPI reaches internal KServe Standard and reports the approved model/package/data lineage;
- KFP bounded run succeeds and creates only a candidate; show the separate approval record used by serving;
- Broker and both Triggers are `Ready=True`; one inference persists in the logging consumer;
- an anomaly persists exactly one alert, including sink-down recovery without a new event and restart recovery from the transactional outbox;
- replay the same CloudEvent after window-state eviction and show deduplication within the seven-day retry horizon;
- show GCS bucket private access/versioning/retention, Workload Identity principals, exact Artifact Registry digests, TLS and enforced NetworkPolicies;
- show node/pod utilization, quotas, budget alerts, current cost and that no Spark resource exists;
- run the full validation matrix against the final commit and scan the final exact images, not predecessor tags.

If monitoring does not fit after required workloads, retain GKE Managed Prometheus/Cloud Logging and omit optional dashboards; record that limitation rather than overcommit nodes.

## 8. Failure, teardown and evidence

Do not destroy on test failure. First export non-secret logs, rendered manifests, KFP/MLflow lineage, alert evidence, image digests, utilization and cost. Teardown needs a separately reviewed plan and explicit owner approval. Remove releases, external load balancers/IPs and NAT, then the cluster. A GCS retention policy cannot be shortened and protected object versions can outlive compute teardown; keep the bucket/state, record its earliest deletion date and residual storage/operation cost, and schedule an owner-approved follow-up. `force_destroy=false` and cluster deletion protection deliberately require conscious changes. Confirm the billing console has no unintended cluster, disk, IP, NAT or load balancer and keep budget alerts active until all retained resources are gone.

### Session start, pause and resume

1. Start: check billing/quota and the reviewed plan, restore `nodes_per_zone=1`, wait for exactly two Ready nodes, then verify the MLflow PVC/SQLite health, GCS access, KFP, KServe Standard and Knative before registering one runner.
2. Pause: stop all jobs, export current evidence, delete the runner Pod/Secret, record PVC/PV/disk/reclaim-policy and load-balancer state, then explicitly approve a regional node-pool resize to zero. This pauses node VMs only; the control plane, disks, GCS, Artifact Registry, load balancers, NAT addresses and logs can remain billable.
3. The manual resize is deliberate Terraform drift from `nodes_per_zone=1`. Do not apply Terraform while paused: it would recreate nodes. Resume by resizing to one node per zone, wait for two Ready nodes, verify the zonal MLflow disk reattaches and SQLite/GCS/KFP state is healthy, then require a no-change plan before further infrastructure work.
4. `emptyDir` and runner state are disposable. MLflow metadata survives only on its PVC; before teardown, take a consistent SQLite backup and export KFP/Helm/resource inventories, exact image/signature/scan evidence, GCS generations, checksums and billing evidence.
5. Authorized teardown: remove external Services/ingress and wait for load-balancer cleanup; delete runner registrations; verify backups; delete PVCs and wait for `Delete`-policy disks or inventory `Retain` disks; separately review/apply `deletion_protection=false`; then separately approve destroy. Do not expect the versioned, retained, `force_destroy=false` model bucket or the separately bootstrapped Terraform-state bucket to disappear.
6. Finish with authenticated read-only inventories for clusters, VMs, disks/snapshots, forwarding rules, IPs, routers/NAT, GCS versions, Artifact Registry, Secret Manager, DNS and logging. Keep alerts active until billing shows only explicitly retained resources.
