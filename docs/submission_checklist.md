# Course submission checklist

**Evidence audit updated 2026-10-27.** Checked items are supported by dated local or CI evidence. A source file or rendered manifest alone does not prove runtime behavior. The authoritative weights are in [`course-rubric-2026.md`](course-rubric-2026.md).

## Weighted technical implementation — 60%

- [x] FastAPI API layer implemented and locally/CI verified — 10% implementation evidence; final KServe path still needs the cloud demo.
- [ ] Real KServe, ModelMesh or KubeRay runtime — 10%.
- [ ] Real Kubeflow Pipelines, Hera or equivalent training run — 15%.
- [ ] Real Knative Broker/Trigger logging flow — 15%.
- [ ] Real-time anomaly detector subscribed through Knative — 10%.

## Selected practical deployment — 40%

- [ ] One authorized GKE cluster running grading-relevant components — 35% selected alternative.
- [ ] MLflow registry artifacts backed by verified GCS object storage — 5%.

The unselected GCE-only 20% alternative is not additive. Private-node GKE, private/versioned GCS, Workload Identity, Artifact Registry, budget and TLS/digest-pinned Helm resources are static definitions only; no cloud plan with credentials or apply has occurred.

## Required deliverables

- [x] GitHub repository with current local installation/testing documentation.
- [ ] README proven from a clean environment through the final cloud flow.
- [ ] Real full-system demonstration video.
- [ ] Evidence index with immutable commit, image, model, dataset, run and artifact identifiers.
- [ ] Safe teardown and final cost evidence.

## Existing supporting engineering evidence

- [x] 152 Pytest tests and 89.41% combined coverage on 2026-10-26.
- [x] Four notebooks executed in prior Module I/II verification.
- [x] DVC reproducibility and MLflow candidate registration.
- [x] Kafka, Bronze, Delta Silver, Trino/dbt Gold, Airflow and Flink/Redis local integration evidence.
- [x] Prometheus, Grafana, Loki and Tempo local runtime evidence.
- [x] Local Terraform/kind/Helm demo release.
- [x] Candidate/approved separation, artifact SHA-256 and packaged provenance checks.
- [x] SEC-022 constrained to accepted-risk local development through 2027-01-23.
- [ ] Image signature and attestation enforcement for cloud deployment.
- [ ] Runtime HPA and KServe scale-to-zero evidence; these are additional engineering targets, not separate supplied rubric points.
- [x] Separate Standard/Knative Helm modes, fail-closed Knative scale-to-zero render and bounded HPA policy are source-tested.
- [x] Protected manual Module I deployment contract uses OIDC and immutable release/model inputs.
- [ ] Qualify the exact KServe 0.21 / Knative 1.23 / Istio 1.31.3 / cert-manager 1.21 / GKE 1.34 candidate in isolation; upstream KServe 0.20/0.21 dependency sets are rejected and deployment fails closed.
- [ ] Run the authorized Module I acceptance report and observe KServe 1→0→1 plus API HPA 2→N→2.
- [ ] Optional bounded 100 GB benchmark; not required for the weighted rubric and not yet run.

## Release gates before the final submission

- [x] PR #13 isolated Kubeflow acceptance tests and evidence pass.
- [ ] Exact synthetic-demo model version and registered artifact digest receive explicit owner approval.
- [x] PR #14 KServe source, local controller and fail-closed tests pass; approved-model runtime remains pending.
- [x] PR #15 isolated Knative logging delivery/retry/dedup/DLQ tests pass.
- [x] PR #16 local normal/anomaly fixtures and recovery tests pass; hardened cloud rerun remains pending.
- [ ] Owner approves a dated GCP calculator estimate, budget alerts and Terraform plan.
- [x] PR #17 offline GKE/GCS source-readiness checks pass; cloud execution remains pending.
- [x] PR #18 clean-run documentation and benchmark safety checks pass; the 100 GB run remains disabled.
- [ ] Module I protected cloud deployment, HPA, Knative scale-to-zero, gateway and hosted observability acceptance pass.
- [ ] No credentials, raw sensitive inputs, mutable image tags or unapproved model artifacts appear in Git/evidence/video.

## Current local quick checks

```bash
uv sync --frozen --all-extras
uv run ruff check src scripts
uv run mypy src/preprocessing_api src/cogniflow_data
uv run pytest src/tests --cov=src/preprocessing_api --cov=src/cogniflow_data --cov-fail-under=81
uv run dvc status
helm lint helm/cognitive-load-monitor
terraform -chdir=infra/terraform/gke validate
```

Do not run `terraform apply`, approve a model or deploy a workload merely to check this list. Follow [`module3/implementation-roadmap.md`](module3/implementation-roadmap.md) and obtain the required owner approvals.

PR #17 offline readiness evidence belongs in [`module3/gke-gcs-readiness.md`](module3/gke-gcs-readiness.md); the exact authorized demo sequence and stop conditions are in [`cloud-deployment.md`](cloud-deployment.md).
