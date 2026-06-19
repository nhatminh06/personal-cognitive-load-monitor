# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.10.0 AS uv
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
ENV PATH="/app/.venv/bin:${PATH}"

COPY src ./src
COPY scripts/download_model_from_mlflow.py ./scripts/download_model_from_mlflow.py
COPY models ./models

ARG MLFLOW_TRACKING_URI=""
ARG MODEL_URI=""
ENV MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI} \
    MODEL_URI=${MODEL_URI} \
    MODEL_PATH=/app/models/cognitive_load_model.joblib

# Requirement hook: when MODEL_URI is provided, the image pulls the model artifact
# from MLflow during build. In local/demo builds, --allow-missing keeps the image
# buildable even before the class MLflow server is configured.
RUN uv run python scripts/download_model_from_mlflow.py \
    --model-uri "${MODEL_URI}" \
    --output "${MODEL_PATH}" \
    --allow-missing

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT}/health || exit 1

CMD ["sh", "-c", "uvicorn preprocessing_api.main:app --host 0.0.0.0 --port ${PORT}"]
