# MLflow and DVC runbook

Use a persistent local SQLite registry and filesystem artifacts:

```bash
uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlartifacts
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 uv run dvc repro
uv run dvc repro  # expected: every stage unchanged
```

The repository DVC remote is local (`.dvc-storage`) and suitable for reproducible offline demonstrations. Do not commit `mlflow.db`, `mlartifacts`, `.dvc-storage`, or model binaries. Deployment must select an exact `models:/cognitive-load-classifier/<version>` URI; aliases and arbitrary pickle discovery are not accepted.
