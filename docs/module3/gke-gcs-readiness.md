# GKE and GCS cloud-readiness design

**Planning snapshot:** 2026-10-26. No GCP resource, credential, model approval, image publication, DNS record or cluster was created or changed.

## One-cluster target

One regional GKE Standard cluster hosts the bounded demonstration. The Terraform defaults place one `e2-standard-4` node in each of two `us-central1` zones (8 vCPU and 32 GiB total). That is a starting capacity gate, not proof that every optional dashboard can coexist. Namespace quotas and measured scheduling must decide whether monitoring is installed or kept to GKE Managed Service for Prometheus and Cloud Logging.

| Namespace | Workloads | Durable data |
|---|---|---|
| `cogniflow` | FastAPI and KServe Standard predictor | none; immutable images contain the approved serving package |
| `kubeflow` | standalone KFP control plane and one serialized training run | KFP metadata PVC; export final run evidence |
| `mlflow` | MLflow tracking/registry and metadata database | encrypted regional persistent disk plus backups; artifacts in private GCS |
| `knative-serving` / `knative-eventing` | Knative controllers, Broker and Triggers | Broker delivery state as provided by the pinned implementation |
| `cogniflow-eventing` | persistent logging consumer, anomaly detector and alert sink | bounded PVCs for logs, detector state and transactional outbox |
| `monitoring` | optional dashboards/collectors only when capacity remains | short bounded retention |

Flow: client → TLS ingress → FastAPI → internal KServe Standard service. FastAPI emits inference CloudEvents to the Knative Broker. Separate Triggers deliver each event to the persistent logging consumer and anomaly detector; alerts enter the detector's transactional outbox and are retried independently to the persistent alert sink. KFP writes candidates to MLflow. Candidate creation never changes approval status. Only the existing explicit approval command may create an approved package, after human review, and deployment requires independently verified package and image digests.

SEC-022 remains local-only. No Spark operator, Spark image, Spark service account, BigLake connector or Spark job belongs in this cluster.

## Compatibility and immutable inputs

Resolve every image/chart to a registry digest and archive the resolution before apply. Tags below identify the compatibility line; tags alone are not deployment evidence.

| Component | Planned line | Reason/gate |
|---|---|---|
| GKE / Kubernetes | Regular channel, Kubernetes `1.34` minimum | Common supported line for the pinned Knative and KServe releases; confirm the exact regional GKE patch immediately before plan |
| KFP standalone | manifests `2.17.2`; SDK `2.17.3` | Matches the locally verified v2 pipeline contract; replace any rendered `master` image before use |
| KServe | controller/CRDs and Python runtime `0.20.0`, Standard mode | Matches Phase 5; no serverless autoscaling dependency |
| Knative Eventing | `1.23.0` | Matches Phase 6/7 evidence and checked-in manifest checksums |
| Knative Serving | `1.23.x` if required by selected KServe install path | Pin exact patch and digests in the reviewed plan |
| cert-manager | `1.18.2` | Matches Phase 5 verification; verify upstream support against the chosen GKE patch |
| ingress-nginx | exact chart/image digest selected at plan time | TLS only; no mutable chart or image reference |
| MLflow / PostgreSQL | repository-locked application version / exact image digests | private services, bounded PVCs and backups required |
| Terraform Google provider | lock file `5.45.2` | `terraform validate` must pass using the committed lock |

GKE currently lists 1.34 in the Regular channel, but availability rolls out per region. Sources: [GKE release notes](https://cloud.google.com/kubernetes-engine/docs/release-notes), [KFP standalone installation](https://www.kubeflow.org/docs/components/pipelines/legacy-v1/installation/standalone-deployment/), [KServe releases](https://github.com/kserve/kserve/releases), and [Knative releases](https://knative.dev/docs/install/).

## Storage, identity and provenance

Terraform creates a dedicated private GCS Standard bucket for MLflow artifacts with uniform bucket-level access, public-access prevention, object versioning, a 30-day retention policy and deletion of noncurrent versions after 45 days. `force_destroy=false` prevents teardown from silently deleting evidence. The MLflow Google service account has bucket-local object administration; the KServe account has bucket-local read only. Kubernetes service accounts impersonate those identities through GKE Workload Identity. No JSON service-account key is accepted.

MLflow's metadata database is not stored in GCS. It requires an encrypted regional persistent disk, scheduled logical backup to a separate protected prefix, restore rehearsal, and a single-writer migration job. The exact database chart is intentionally an install-time choice because no database deployment exists in this repository yet; that is a deployment blocker, not permission to use SQLite for a cloud registry.

Artifact paths are immutable by convention: `candidates/<model>/<run-id>/<artifact-digest>/...` and `approved/<model>/<version>/<package-digest>/...`. The promotion record must include source revision, KFP run, dataset/schema/model/artifact/package SHA-256 values, approver and timestamp. KServe receives read-only access and deploys only an explicitly approved package; candidates remain non-deployable.

## Security boundaries

- Private GKE nodes use a dedicated VPC/subnet, Private Google Access and logged Cloud NAT. The public control-plane endpoint is restricted to explicit `/32` operator/VPN ranges.
- Dataplane V2 enforces NetworkPolicy. The Helm policy permits API ingress only from ingress-nginx/monitoring and egress only to DNS, KServe, Knative Eventing and OTLP. Apply namespace default-deny and reviewed component policies before installing KFP, MLflow, Knative or event consumers.
- Images come from private Artifact Registry and are referenced by `sha256` digest. Node read and GitHub publisher roles are repository-scoped.
- TLS and an externally created authentication Secret are mandatory for production ingress. Terraform creates only Secret Manager metadata, never a secret version. An approved operator must create the version and sync/mount it into Kubernetes; plaintext values never enter Terraform, Git or Helm values.
- Workloads retain non-root, read-only-root-filesystem, dropped-capability and bounded-request/limit settings. Pod Security Admission `restricted`, ResourceQuota and LimitRange are pre-deployment gates.
- GitHub OIDC accepts only this repository's `main` ref. Branch protection and a protected production environment with required reviewers remain mandatory before credentials are configured.

## Terraform state finding

Only metadata was inspected; state contents were deliberately not read.

| Local ignored file | Mode | Size | Last modified |
|---|---:|---:|---|
| `infra/terraform/local/cluster/terraform.tfstate` | `0644` | 12,343 B | 2026-10-25 19:57 |
| `infra/terraform/local/cluster/terraform.tfstate.backup` | `0644` | 768 B | 2026-10-25 19:57 |
| `infra/terraform/local/app/terraform.tfstate` | `0644` | 6,119 B | 2026-10-25 19:59 |

Recent timestamps make these active-looking, but ownership cannot be established without opening state or contacting its operator. Their world-readable mode is a blocker. The owner should first identify the active operator, then restrict state files to `0600` and containing directories to `0700`; rotate any credential later confirmed to have appeared in state. Do not delete or rewrite these files.

For GKE use a separately bootstrapped GCS backend (see `backend.tf.example`) with uniform access, public-access prevention, versioning, retention, CMEK if policy requires it, and least-privilege state administrators. Keep state and application artifact buckets separate. Migration and any backend lock/change require owner review and a recoverable backup.

## Approval boundary

Explicit owner approval is required before enabling billing/APIs; creating a backend, budget, IAM binding, bucket, registry, network, IP, NAT, load balancer, DNS, certificate or cluster; adding a Secret Manager version; applying/destroying Terraform; publishing/signing an image; approving/deploying a model; or exposing an endpoint. `terraform plan` must show only the intended project and no local-state migration. No approval is implied by this design.

## Observed offline verification

On 2026-10-26 America/Chicago, the branch passed 287 Pytest tests with 88.76% combined coverage (81% gate), Ruff, scoped MyPy over 27 source files, KFP compilation with a synthetic immutable Artifact Registry digest, Terraform formatting/validation, Helm lint and exact-digest production rendering, Actionlint, and parsing of all 13 checked deployment/workflow YAML files. The three cloud-readiness regressions cover private/storage/identity Terraform controls, exact images/TLS/separate service accounts/narrow policies, and fail-closed placeholders.

Trivy 0.76.1 found zero High/Critical misconfigurations in the GKE Terraform and Helm chart. Gitleaks 8.30.1 found no leak in the current directory scan; the 58-commit history scan retained three previously documented false positives from historical Basic Auth shell-variable examples. No final Artifact Registry image exists, so no PR #17 final image scan was possible; this PR changes no application image content.

`dvc status` ran and reported the known Phase 2 source-revision drift: `data/processed/module3/training_manifest.json` is modified relative to `phase2_dataset`, so `phase2_train` sees that dependency changed. No DVC reproduction or model retraining was performed because this planning PR must not create or imply a newly approved candidate. No credential-backed Terraform plan, GKE/GCS runtime, cost, image publication, secret version, model approval or teardown occurred.
