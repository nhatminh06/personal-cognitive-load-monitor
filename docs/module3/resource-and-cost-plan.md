# Module III resource and cost plan

**Planning estimate dated 2026-10-26; no cloud resources were created.** Recalculate with the Google Cloud Pricing Calculator immediately before approval because regions, versions and prices change.

## Resource strategy

| Component | Planning reservation for a small demonstration | Independent test path | Coexistence notes |
|---|---:|---|---|
| Kubeflow Pipelines standalone control plane | 2–4 vCPU, 4–8 GiB RAM, persistent metadata/artifact storage | Compile locally; run separately in an isolated cluster/namespace | Install standalone KFP, not the full Kubeflow platform |
| One KFP training run | 2–4 vCPU, 4–8 GiB peak RAM | Run after control plane is healthy; serialize heavy steps | Keep datasets bounded; no Spark runtime in GKE |
| KServe + Knative Serving | 1–2 vCPU, 2–4 GiB control-plane RAM plus model pod | Test custom model server as a local container first | Exact consumption depends on deployment mode and autoscaler |
| Knative Eventing + Broker | 1–2 vCPU, 2–4 GiB RAM | Test schemas/consumers locally; install after serving verification | Broker implementation choice materially changes cost |
| FastAPI, logging consumer and anomaly detector | 1–2 vCPU, 1–3 GiB RAM total | Unit/container tests independently | Use small bounded replicas for the demonstration |
| MLflow + metadata database | 1–2 vCPU, 2–4 GiB RAM | Existing local registry remains usable for component tests | GCS holds artifacts; metadata needs durable storage/backups |
| Monitoring and cluster/system headroom | 2–4 vCPU, 4–8 GiB RAM | Reuse local observability sequentially | Do not schedule to 100%; reserve failure/restart headroom |

These are initial reservation ranges, not measured vendor minima. Capture actual requests, limits and peak usage during PRs #13–#16 and revise before PR #17.

The current limited-RAM workstation should not run KFP, KServe/Knative, the Module II lakehouse and observability stack simultaneously. Safe local work is sequential:

1. Compile and unit-test KFP components without a cluster.
2. Start only standalone KFP for one bounded pipeline integration; stop it afterward.
3. Test the custom serving container without KServe.
4. Start KServe/Knative in an isolated environment only when host memory and swap have safe headroom.
5. Test Eventing consumers and detector independently, then perform a combined rehearsal on adequately sized GKE.

Preserve PersonalOS on host port `8000`, the existing CogniFlow demonstration on `18000`, and experimental serving on `18001`. Never recreate the existing kind cluster merely to install heavier components.

## Minimum viable GKE topology

Start planning with one regional GKE Standard cluster and a dedicated autoscaling node pool. The existing example (`2 × e2-standard-2`) is not accepted as adequate until scheduling tests prove it. A realistic first calculator scenario is two nodes with roughly 8 vCPU/32 GiB each, plus autoscaling limits and resource quotas. A cheaper single-node rehearsal reduces resilience and cannot prove node-failure behavior; it may be used only when the acceptance scope says so.

Use namespaces for `cogniflow-api`, `cogniflow-serving`, `kubeflow`, `knative-serving`, `knative-eventing`, `mlflow` and observability. Schedule one bounded training run at a time. Scale optional dashboards down outside the recording window. Do not deploy SEC-022 Spark.

Compatibility must be proven with a pinned matrix covering Kubernetes/GKE, KFP, KServe, Knative Serving/Eventing, cert-manager/networking and the custom Python runtime before Terraform apply.

## Cost scenarios

Google currently lists a GKE cluster-management fee of **$0.10 per cluster-hour** and a monthly free-tier credit equivalent to one zonal or Autopilot cluster's management fee, subject to eligibility. Standard-cluster worker nodes are billed as Compute Engine instances. Cloud Storage Standard in `us-central1` is about **$0.02/GiB-month** (`$0.000027397/GiB-hour`) plus operations and any network transfer.

| Scenario | Assumptions | Planning envelope, USD | Use |
|---|---|---:|---|
| Local component work | Existing workstation; sequential services; no paid cloud | $0 cloud | PRs #12–#16 where resources permit |
| One 8-hour GKE rehearsal | One cluster; 2 medium/large general-purpose nodes; small disks; low traffic; same-region GCS | **$8–$20** | Install/compatibility and one pipeline/serving rehearsal |
| One 24-hour full demo window | Same cluster; 2 nodes near 8 vCPU/32 GiB each; monitoring; load balancer; under 20 GiB artifacts | **$25–$60** | PR #17 evidence and recording rehearsal |
| Three-day validation buffer | Same topology with limited autoscaling and repeated runs | **$75–$180** | Failure/recovery, final recording and contingency |

The envelopes are deliberately conservative planning limits, not Google quotes. Compute, persistent disks, load balancers, logging ingestion, Artifact Registry, NAT and egress vary by region and topology. Before approval, save a dated calculator estimate using the exact region/machine types and set the budget below the owner's maximum. Storage is expected to be cents for bounded artifacts; compute and managed networking dominate.

Sources:

- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing)
- [Compute Engine pricing](https://cloud.google.com/products/compute/pricing)
- [Cloud Storage pricing](https://cloud.google.com/storage/pricing)
- [Kubeflow Pipelines standalone installation](https://www.kubeflow.org/docs/components/pipelines/legacy-v1/installation/standalone-deployment/)

## Cost controls and lifecycle

Before creation:

- require explicit owner approval for project, region, calculator estimate, budget ceiling and maximum lifetime;
- configure billing budget alerts (for example 25%, 50%, 75%, 90% and 100%) and an independent calendar expiry;
- produce and review `terraform plan`; label every owned resource with project/module/expiry where supported;
- use bounded fixture sizes, registry retention and log exclusions; prohibit the 100 GB benchmark during the grading deployment;
- select same-region GKE, GCS and Artifact Registry to limit transfer charges.

During the window, capture cluster/node/pod utilization and current accrued cost after each major phase. Stop failed experiments promptly; do not keep idle nodes alive merely to preserve screenshots.

Cleanup order: export non-secret evidence → remove application releases → remove KFP/KServe/Knative resources owned by the deployment → verify buckets/registry retention requirements → run a reviewed Terraform destroy against only the PR #17 state → verify no billable cluster, disk, IP, load balancer or NAT remains. Bucket/artifact deletion requires its own retention decision; never use a broad recursive delete.

## Operations requiring explicit owner approval

- creating or changing a GCP project, billing account, budget or alert;
- `terraform apply` or `terraform destroy` against GCP;
- creating GKE, GCS, Artifact Registry, external IP, load balancer, NAT, DNS or managed certificate resources;
- granting IAM roles, creating Workload Identity bindings or changing organization policy;
- approving a model version, deploying a model, publishing/signing an image or exposing an endpoint;
- recording or publishing the video/evidence where account identifiers may appear;
- extending the deployment beyond its approved expiry or cost ceiling.

Local lint, compile, unit tests, manifest rendering and read-only inspection do not grant authority for any operation above.
