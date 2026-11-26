# CogniFlow

[![CI](https://github.com/nhatminh06/personal-cognitive-load-monitor/actions/workflows/ci-cd.yaml/badge.svg)](https://github.com/nhatminh06/personal-cognitive-load-monitor/actions/workflows/ci-cd.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

CogniFlow is an educational data-engineering and MLOps platform built around a
synthetic cognitive-load classifier. LOW, MEDIUM and HIGH are deterministic proxy
labels, not clinical or real-world measurements. Do not use the project for
diagnosis, employee monitoring, academic decisions or other decisions about people.

**Public V0.1:** [Open CogniFlow](https://cogniflow.minhpham06.com) ·
[workers.dev preview](https://cogniflow-v01.mphamnhat2006.workers.dev).
The deployed TypeScript Cloudflare Worker serves the dashboard and authenticated
focus-session API; D1 stores sessions, events, labels and synthetic estimates.
Owner login, start/pause/resume/complete, five-minute windows, effort ratings,
timeline and `demo_rule` estimates are available. Estimates are synthetic proxies,
not model predictions.

## Deployed MVP and future platform

V0.1 runs only on Cloudflare Workers, Static Assets and D1. Its owner-only browser
login uses host-only Secure, HttpOnly, SameSite=Strict cookies, exact-origin CSRF
checks and rate limits. The Linux FastAPI MVP is a separate local deployment.
Kafka, Flink, Spark, KFP, KServe and the components below are future or frozen
research paths; they do not process traffic for the public V0.1 Worker.

- Module II: Kafka → SeaweedFS Bronze → Spark/Delta Silver → Trino/dbt Gold,
  orchestrated by Airflow; Flink maintains Redis online features.
- Module III: KFP → MySQL/MLMD → MLflow → explicit model approval → KServe;
  Knative Eventing feeds persistent anomaly detection and alerting.
- The Linux MVP uses Docker Compose. Kubernetes and Terraform material are frozen
  research, not an active public deployment route.

Local evidence does not prove GKE/GCS operation. SeaweedFS equivalence to an
explicit MinIO course requirement is unresolved. The SEC-022 Spark image is
development-only and forbidden in Kubernetes or GKE. No model is approved for
production serving.

## Release evidence and limits

The TypeScript and Python HTTP contract matched on 35 paired requests. Local D1
race tests covered 30 groups of three identical creates with one 201 and two 200
responses per group. The retained live Free-plan CPU qualification matched 240/240
invocation logs; its maximum reported CPU was 8 ms. A separate earlier sampled
run observed 8.744 ms. The final dual-host release checks passed HTTPS, owner
login/logout, session lifecycle, timeline,
cross-host D1 persistence, CSRF rejection and desktop/mobile Chromium rendering.
Recent aggregate metrics showed 201 requests and zero Worker errors. These are
bounded observations, not a guarantee against future Free CPU or daily quota limits.
Persistent Worker invocation/application logs and traces are disabled; older
qualification logs expire under Cloudflare retention. Actual billable charges
remain unverified even though Workers Free is active and no paid feature was enabled.
See the [deployment report](docs/readiness/cogniflow-v01-cloudflare-free-deployment.md)
for methods, timestamps and limitations.

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
cd deploy/cloudflare && node --test tests/d1-atomic.mjs
```

## Documentation

- [Architecture](docs/architecture.md)
- [Module II data platform](docs/module2.md)
- [Module III training and serving](docs/module3.md)
- [Cloudflare V0.1 deployment](docs/readiness/cogniflow-v01-cloudflare-free-deployment.md)
- [Historical deployment research](docs/deployment.md)
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

Ordinary CI cannot publish the Cloudflare Worker or create D1 resources.
Publication requires the owner authorization described in the Cloudflare V0.1 report.

Original CogniFlow code is licensed under [MIT](LICENSE). Dependencies retain their
own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
