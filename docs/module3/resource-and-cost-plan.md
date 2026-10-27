# Module III GKE resource and cost plan

**Estimate:** 2026-10-26 USD public list prices; no cloud resource was created. Recalculate the exact reviewed plan immediately before approval.

## Bounded topology

The Terraform default is one regional Standard cluster with one `e2-standard-4` node in each of two `us-central1` zones: 8 vCPU and 32 GiB total. Private nodes use Cloud NAT. GCS and Artifact Registry are co-located. Required services are FastAPI, KServe Standard, Knative Eventing/Serving, one bounded KFP run, MLflow/PostgreSQL, the persistent logging consumer and anomaly detector/sink. GKE Managed Prometheus and Cloud Logging are the baseline; optional in-cluster dashboards install only after measured scheduling leaves restart headroom.

| Capacity slice | Initial request envelope |
|---|---:|
| GKE/KFP/KServe/Knative controllers | 2.5–4 vCPU, 8–12 GiB |
| one serialized training run | 2 vCPU, 4–6 GiB |
| FastAPI + KServe predictor | 1–1.5 vCPU, 2–3 GiB |
| MLflow + PostgreSQL | 1 vCPU, 3–4 GiB |
| event logging + anomaly detector/sink | 0.5–1 vCPU, 1–2 GiB |
| system/restart headroom | at least 1 vCPU, 4 GiB |

`deploy/gke/resource-budget.yaml` is the offline gate: total required requests must fit within 80% of two-node capacity. The current plan reserves 20% for GKE/system/restarts, serializes the training run and excludes optional dashboards. This arithmetic is not scheduler proof; before apply, render every pinned add-on and replace estimates with summed requests. If the gate fails, omit optional components or obtain approval for a larger node pool. Do not silently enable autoscaling or add nodes. SEC-022 Spark is prohibited in GKE.

## Current price basis

- GKE management: `$0.10/cluster-hour`; the free-tier credit applies to eligible zonal/Autopilot clusters, not this regional cluster.
- Two on-demand `e2-standard-4` nodes in Iowa: `2 × $0.13402284 = $0.26804568/hour` before disks.
- Public Cloud NAT for two VMs: `2 × $0.0014/hour`, plus `$0.005/hour` for one IP and `$0.045/GiB` processed.
- Regional GCS Standard: `$0.000027397/GiB-hour` (about `$0.02/GiB-month`), plus operations.
- Artifact Registry: first 0.5 GiB-month free per billing account, then `$0.000136986/GiB-hour` (about `$0.10/GiB-month`); same-region transfer is free.
- Cloud Logging: first 50 GiB/project/month free, then `$0.50/GiB` for default retention. Load balancer, persistent disks, DNS/certificate, monitoring samples, scanning and Internet egress are additional.

Official sources: [GKE](https://cloud.google.com/kubernetes-engine/pricing), [E2 VM](https://cloud.google.com/products/compute/pricing/general-purpose), [Cloud NAT](https://cloud.google.com/nat/pricing), [Cloud Storage](https://cloud.google.com/storage/pricing), [Artifact Registry](https://cloud.google.com/artifact-registry/pricing), and [Cloud Logging](https://cloud.google.com/logging).

## Scenarios and budget

The directly priced base is about `$0.376/hour` before disks, load balancing, storage operations and traffic. Allowing those variable services and setup inefficiency gives these deliberately conservative envelopes:

| Scenario | Lifetime | Planning envelope |
|---|---:|---:|
| Install/scheduling rehearsal | 8 hours | **$6–$12** |
| Full evidence rehearsal | 24 hours | **$15–$30** |
| Three-day contingency | 72 hours | **$45–$90** |
| Accidental full month | 730 hours | **$300–$375+** |

The Terraform `$100` project-scoped budget with alerts at 25/50/75/90/100% is a mandatory approved plan input, but budgets do not stop spend. Owner approval covers only the initial eight-hour window. Set an independent calendar expiry and check billing after each phase. The plan must use bounded fixtures, short log retention/exclusions, same-region data, repository cleanup rules reviewed against evidence retention, and no 100 GB benchmark.

## Teardown boundary

Export non-secret evidence first. Teardown needs a new reviewed plan and explicit approval. Remove releases and billable load balancers/IPs/NAT, then the cluster. Preserve state and protected model evidence according to retention; the bucket has `force_destroy=false` and the cluster has deletion protection. Versioned objects under the 30-day retention lock cannot be deleted early, so record the earliest eligible deletion date and continue reporting GCS residual cost until an owner-approved follow-up removes them. Confirm the billing console shows no unintended cluster, disks, IPs, load balancers or NAT. Never recursively delete a bucket or touch the local Terraform state trees.
