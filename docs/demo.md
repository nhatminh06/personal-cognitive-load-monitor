# Demo and verification

## Local API

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

The expected demo-rule response is authenticated and uses synthetic inputs. A
missing API key must return 401.

## Engineering checks

```bash
uv lock --check --offline
make test
uv run ruff check src scripts dags pipelines
helm lint helm/cognitive-load-monitor
terraform -chdir=infra/terraform/gke validate
```

Compile the KFP pipeline with `scripts/compile_kfp_pipeline.py` and compare it to
`pipelines/compiled/cogniflow-training.yaml`. Render deployment manifests only
with reviewed immutable image inputs. Module II uses its isolated rehearsal
script and Compose profiles; do not run Spark and Flink concurrently on a small
developer host.

This demo does not approve a model, deploy Kubernetes, use GCP or publish images.
