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

COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
RUN python -m pip uninstall -y pip setuptools
ENV PATH="/app/.venv/bin:${PATH}"

COPY src ./src
COPY models ./models

ENV MODEL_PATH=/app/models/cognitive_load_model.joblib

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)" || exit 1

CMD ["sh", "-c", "uvicorn preprocessing_api.main:app --host 0.0.0.0 --port ${PORT}"]
