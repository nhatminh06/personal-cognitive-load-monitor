# Course submission checklist

**Evidence audit updated 2026-10-26.** Checked items are supported by dated local or CI evidence. A source file or rendered manifest alone does not prove runtime behavior. The authoritative weights are in [`course-rubric-2026.md`](course-rubric-2026.md).

## Weighted technical implementation — 60%

- [x] FastAPI API layer implemented and locally/CI verified — 10% implementation evidence; final KServe path still needs the cloud demo.
- [ ] Real KServe, ModelMesh or KubeRay runtime — 10%.
- [ ] Real Kubeflow Pipelines, Hera or equivalent training run — 15%.
- [ ] Real Knative Broker/Trigger logging flow — 15%.
- [ ] Real-time anomaly detector subscribed through Knative — 10%.

## Selected practical deployment — 40%

- [ ] One authorized GKE cluster running grading-relevant components — 35% selected alternative.
- [ ] MLflow registry artifacts backed by verified GCS object storage — 5%.

The unselected GCE-only 20% alternative is not additive. GKE Terraform and GCS resources are currently static definitions only; no cloud apply has occurred.

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
- [ ] Optional bounded 100 GB benchmark; not required for the weighted rubric and not yet run.

## Release gates before the final submission

- [ ] PR #13 Kubeflow acceptance tests and evidence pass.
- [ ] Exact synthetic-demo model version and registered artifact digest receive explicit owner approval.
- [ ] PR #14 KServe acceptance tests and fail-closed cases pass.
- [ ] PR #15 Knative logging delivery/retry/dedup/DLQ tests pass.
- [ ] PR #16 normal/anomaly fixtures and detection-latency SLO pass.
- [ ] Owner approves a dated GCP calculator estimate, budget alerts and Terraform plan.
- [ ] PR #17 GKE/GCS end-to-end, security, cost and teardown evidence pass.
- [ ] PR #18 clean-run documentation and [`demo/full-rubric-demo.md`](demo/full-rubric-demo.md) recording checklist pass.
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
