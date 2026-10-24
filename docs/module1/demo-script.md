# Reproducible demo

```bash
uv sync --frozen --all-extras
DVC_SITE_CACHE_DIR=/tmp/cogniflow-dvc uv run dvc repro
INFERENCE_MODE=demo_rule uv run uvicorn --app-dir src preprocessing_api.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, submit the form, confirm the result names `demo_rule`, then inspect `/model-info`, `/docs`, `/health`, `/ready`, and `/metrics`. For `local_model`, set `MODEL_PATH`, `MODEL_VERSION`, and `INFERENCE_MODE=local_model`. For KServe, set `INFERENCE_MODE=kserve` and `KSERVE_PREDICT_URL`; an outage must return 503/504, never a rule result.
