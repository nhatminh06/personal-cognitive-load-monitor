# GKE/GCS deployment and final-demo runbook

**Status:** planning and offline validation only, 2026-10-26. Nothing in this runbook has been applied to GCP. Read [the cloud-readiness design](module3/gke-gcs-readiness.md) first.

## 1. Owner approvals and release inputs

Record approvals for project/billing account, `us-central1`, a maximum **$100** monthly budget alert (alerts do not cap spend), an eight-hour initial lifetime, remote state, IAM, DNS/TLS, image publication and the exact Terraform plan. Model approval is separate and is not granted here.

Required immutable inputs:

- exact GKE version available in both planned zones;
- reviewed add-on manifest/chart digests from the compatibility matrix;
- API, KServe, event consumer and anomaly images in Artifact Registry by registry digest;
- candidate lineage and approved package digests, only if an authorized owner has separately approved a model;
- operator/VPN `/32`, owned hostname, certificate issuer and Secret Manager/Kubernetes secret-sync procedure.
- fixed `/32` egress for the dedicated self-hosted deployment runner; GitHub-hosted runners are forbidden because their changing source ranges do not fit master-authorized networks;
- approved project-scoped budget alerts, PostgreSQL/backup digests and a passing two-node resource-budget check.

Stop if GitHub `main` is not branch-protected, the deploy environment lacks required reviewers, the fixed runner cannot reach the authorized endpoint, any image uses a tag without a digest, a signature/scan fails, a manifest renders `:master`, capacity does not fit, the budget is absent, or a Terraform target differs from the approved project.

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

Create an untracked tfvars file from the example. Set the project, two zones in the same region, operator and dedicated-runner `/32` addresses, GitHub repository, owner-approved billing account and numeric project number. Terraform intentionally refuses a plan without the budget inputs.

```bash
terraform -chdir=infra/terraform/gke plan -out=PR17-REVIEW-ONLY.tfplan
terraform -chdir=infra/terraform/gke show PR17-REVIEW-ONLY.tfplan
```

Review resource count, region, IAM members, private nodes, authorized networks, retention, `force_destroy=false`, deletion protection and estimated cost. Never commit the plan (it can contain sensitive values). A changed plan invalidates approval.

## 4. Authorized provisioning and cluster gates

Only an authorized operator may apply the exact reviewed plan. Immediately confirm two private nodes, Workload Identity, Dataplane V2, Cloud Logging/Managed Prometheus, only reviewed `/32` control-plane networks, budget alerts and Artifact Registry/GCS public-access prevention. Dataplane V2 already enables policy enforcement; do not add the incompatible GKE `network_policy` switch. A bootstrap cluster administrator substitutes the reviewed project ID and applies `deploy/gke/cogniflow-guardrails.yaml`; the deployment identity then has namespace admin only. Apply the eventing namespace/policy before its workloads.

Install pinned cert-manager, ingress-nginx, Knative Serving/Eventing, KServe Standard and standalone KFP in compatibility order. Resolve every deployed image ID and compare it with the evidence ledger. Reject mutable `master`, `latest` or SHA-shaped tags.

Deploy the reviewed PostgreSQL 17.6 design and MLflow 3.17.2 privately by exact digest. Bind `mlflow/mlflow` to the Terraform MLflow Google service account. Prove a write/read round trip to `gs://<model_bucket>/candidates/...`, run the daily custom-format backup, and restore it into an isolated validation database before training. Install External Secrets Operator chart 2.13.0 by reviewed digest. Apply `deploy/gke/external-secret.yaml` before Helm; it can reconcile after Helm creates `cogniflow-api`. Verify only the expected Secret keys, without printing values.

## 5. Candidate training and explicit promotion

Submit one bounded KFP run by immutable component digest. Confirm all six tasks, dataset digest, KFP run ID and MLflow candidate tags. A successful run must remain `candidate`; it must not update an alias/stage used by serving.

Pause for independent human review. If and only if the authorized owner approves the exact version, run the existing approval/package workflow, copy the verified package under `approved/.../<package-digest>/`, and record the approver and all lineage digests. Any digest mismatch stops deployment.

## 6. Digest-pinned application deployment

An approved operator creates the Secret Manager secret version and the external Kubernetes Secrets without printing values. Render first; the checked-in sentinels must fail closed.

The manual `.github/workflows/release.yaml` job uses the separately protected
`production-release` environment and a release-only Google service account. It
does not approve models or deploy: `package_approved_model.py` first requires an
independently approved exact MLflow version and artifact-tree digest. The job
then builds the API, KServe, event-consumer and anomaly images once, resolves
their Artifact Registry digests, emits BuildKit SBOM/provenance attestations,
and uses Cosign 3.1.4 keyless signing with GitHub OIDC. It verifies each
signature and runs Trivy 0.76.1 against that same digest before retaining the
non-secret evidence. The main-push job in `ci-cd.yaml` remains a GHCR CI build;
it is not a production release.

Provisioning the `cogniflow-release` runner, configuring required reviewers on
`production-release`, and setting its `GCP_RELEASE_WORKLOAD_IDENTITY_PROVIDER`,
`GCP_RELEASE_SERVICE_ACCOUNT`, `MLFLOW_TRACKING_URI`, `GCP_PROJECT_ID`, and
`GAR_LOCATION` values remain owner-controlled pending operations. The Terraform
OIDC bindings separate the `production-release` publisher from the `production`
deployer and bind each impersonation grant to its environment. On the dedicated
deploy runner, `scripts/verify_cloud_release.sh` re-verifies the release identity
and runs Trivy against the exact digests before Helm.

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
separate protected deployment action.

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
