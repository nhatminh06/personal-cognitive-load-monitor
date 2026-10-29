# Module I demonstration

The final demonstration has two deliberately separate stages.

## Safe local stage

```bash
uv sync --frozen --all-extras
DVC_SITE_CACHE_DIR=/tmp/cogniflow-dvc uv run dvc status
INFERENCE_MODE=demo_rule uv run uvicorn --app-dir src \
  preprocessing_api.main:app --host 127.0.0.1 --port 8000
```

Show the four notebooks, DVC stages, Evidently report, authenticated FastAPI
contract, `/model-info`, `/health`, `/ready`, `/metrics`, and the previously
recorded Prometheus/Grafana/Loki/Tempo evidence. `demo_rule` proves API behavior
only; it is not approved-model or KServe evidence.

## Separately authorized cloud stage

Follow [`final-acceptance.md`](final-acceptance.md) exactly. Use the protected
Module I workflow and one approved model/release identity. Demonstrate the
NGINX 401/200 boundary, model provenance, KServe `Ready=True`, independent
predictor positive→0→positive behavior with a successful cold-start prediction, independent
FastAPI HPA 2→N→2 behavior under bounded load, and correlated metric/log/trace
evidence. Stop at any identity, health, error-rate, capacity or cost mismatch.

Do not substitute Standard-mode KServe, a contract responder, YAML rendering,
Eventing scale-to-zero, or a demo-rule response for Knative serving evidence.
