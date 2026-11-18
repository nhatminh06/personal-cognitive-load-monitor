# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.10.0@sha256:78a7ff97cd27b7124a5f3c2aefe146170793c56a1e03321dd31a289f6d82a04f AS uv
FROM cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90 AS build

RUN apk add --no-cache python-3.13=3.13.18_git20261115-r1

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --python /usr/bin/python3.13 --frozen --no-dev --no-install-project

FROM cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90 AS runtime

RUN apk add --no-cache python-3.13=3.13.18_git20261115-r1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8000

WORKDIR /app
COPY --from=build --chown=65532:65532 /app/.venv ./.venv
ENV PATH="/app/.venv/bin:${PATH}"

COPY --chown=65532:65532 src ./src
COPY --chown=65532:65532 models ./models

ENV MODEL_PATH=/app/models/cognitive_load_model.joblib

USER 65532

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

ENTRYPOINT ["/app/.venv/bin/python", "-m", "uvicorn"]
CMD ["preprocessing_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
