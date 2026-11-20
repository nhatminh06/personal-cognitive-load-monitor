# CogniFlow maintenance

Preserve unpublished commits, DVC data, unique qualification evidence and unrelated changes.
Never mutate the retained `cogniflow-local` or `cogniflow-module1-qualification` clusters.
Cloud, registry publication, remote Git writes and model approval require explicit authorization.

Canonical paths:

- Module II: `src/cogniflow_data`, `jobs`, `dags`, `analytics`, `infra/module2`.
- Training: `pipelines/cogniflow_training_pipeline.py`, `src/cogniflow_data/kfp_tasks.py`.
- Qualified training build: `deploy/c23/kfp-component`; headless KFP: `infra/kfp-local`.
- Serving/eventing: `src/cogniflow_kserve`, `src/preprocessing_api`, `src/cogniflow_eventing`, `src/cogniflow_anomaly`.
- GKE: `infra/terraform/gke`, `deploy/gke`, `helm/cognitive-load-monitor`.
- Tests: `src/tests`; evidence index: `docs/course-completion/evidence-index.md`.

Run `make test`, `.venv/bin/ruff check src scripts jobs dags pipelines`, Helm lint,
Compose config validation and backend-free Terraform validation for relevant changes.
Keep source and compiled KFP YAML synchronized. Distinguish static, unit, container,
Kubernetes and cloud results; never promote historical evidence to a fresh pass.
SEC-022 permits only its recorded isolated local Spark scope, never GKE.
