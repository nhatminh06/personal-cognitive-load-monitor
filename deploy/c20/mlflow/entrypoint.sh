#!/bin/sh
set -eu

: "${MLFLOW_BACKEND_STORE_URI:?required}"
: "${MLFLOW_ARTIFACTS_DESTINATION:?required}"

exec /venv/bin/mlflow server \
  --host 0.0.0.0 \
  --port 5000 \
  --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
  --artifacts-destination "$MLFLOW_ARTIFACTS_DESTINATION" \
  --serve-artifacts \
  --workers 1 \
  --allowed-hosts "${MLFLOW_ALLOWED_HOSTS:-localhost:5000,127.0.0.1:5000}"
