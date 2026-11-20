# CogniFlow

[![CI](https://github.com/nhatminh06/personal-cognitive-load-monitor/actions/workflows/ci-cd.yaml/badge.svg)](https://github.com/nhatminh06/personal-cognitive-load-monitor/actions/workflows/ci-cd.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

CogniFlow is an educational data-engineering and MLOps platform built around a
synthetic cognitive-load classifier. LOW, MEDIUM and HIGH are deterministic proxy
labels, not clinical or real-world measurements. Do not use the project for
diagnosis, employee monitoring, academic decisions or other decisions about people.

## Platform

- Module II: Kafka → SeaweedFS Bronze → Spark/Delta Silver → Trino/dbt Gold,
  orchestrated by Airflow; Flink maintains Redis online features.
- Module III: KFP → MySQL/MLMD → MLflow → explicit model approval → KServe;
  Knative Eventing feeds persistent anomaly detection and alerting.
- Delivery: Docker/Compose, Helm, Kubernetes and Terraform configuration with
  fail-closed security and publication gates.

Local evidence does not prove GKE/GCS operation. SeaweedFS equivalence to an
explicit MinIO course requirement is unresolved. The SEC-022 Spark image is
development-only and forbidden in Kubernetes or GKE. No model is approved for
production serving.

## Run the local API

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen --all-extras
export COGNIFLOW_API_KEY=local-demo-key
export INFERENCE_MODE=demo_rule
uv run uvicorn --app-dir src preprocessing_api.main:app --host 127.0.0.1 --port 8000
```

```bash
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: ${COGNIFLOW_API_KEY}" \
  -d '{"focus_minutes":180,"distraction_minutes":60,"tasks_due":3,"hours_to_deadline":24}' \
  http://127.0.0.1:8000/predict
```

## Verify

```bash
uv lock --check --offline
make test
uv run ruff check src scripts dags pipelines
helm lint helm/cognitive-load-monitor
terraform -chdir=infra/terraform/gke validate
```

## Documentation

- [Architecture](docs/architecture.md)
- [Module II data platform](docs/module2.md)
- [Module III training and serving](docs/module3.md)
- [Deployment and release](docs/deployment.md)
- [Security](docs/security.md)
- [Evidence index](docs/evidence.md)
- [Demo](docs/demo.md)
- [Data card](docs/data-card.md)
- [Model card](docs/model-card.md)
- [Responsible use](docs/responsible-use.md)
- [Course rubric](docs/course-rubric-2026.md) and
  [submission checklist](docs/submission_checklist.md)

Application code lives in `src/`, tests in `src/tests/`, pipeline and deployment
configuration in `pipelines/`, `deploy/`, `helm/` and `infra/`. Machine-readable
schemas and qualification evidence remain under `docs/` even where historical
narrative reports were removed.

## Release boundary

Ordinary CI cannot publish images, authenticate to cloud providers or deploy
infrastructure. Publication and cloud deployment require explicit approval of the
exact revision, destination, Terraform plan, image identities, model decision and
teardown procedure.

Original CogniFlow code is licensed under [MIT](LICENSE). Dependencies retain their
own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
