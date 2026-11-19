# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.10.0@sha256:78a7ff97cd27b7124a5f3c2aefe146170793c56a1e03321dd31a289f6d82a04f AS uv
FROM cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90 AS build

ADD --checksum=sha256:4b50a172728854115776532673e0df6d98679fb8303a806d901bb7825e359e55 \
    https://github.com/kubeflow/pipelines/archive/7dd28116ad652bfb7b6c282e7920be84e6a7634a.tar.gz /tmp/kfp.tar.gz
RUN apk add --no-cache python-3.13=3.13.18_git20261115-r1 \
    && mkdir /source \
    && tar -xzf /tmp/kfp.tar.gz --strip-components=1 -C /source
COPY --from=uv /uv /bin/uv
COPY requirements.txt /requirements.txt
RUN uv venv --python /usr/bin/python3.13 /venv \
    && uv pip install --python /venv/bin/python --no-cache --require-hashes -r /requirements.txt

FROM cgr.dev/chainguard/wolfi-base@sha256:580c9ae79c0229cc381475fbfbed0d91fab5d6606e57cd78732f9836de109e90
RUN apk add --no-cache python-3.13=3.13.18_git20261115-r1
COPY --from=build --chown=65532:65532 /venv /venv
COPY --from=build --chown=65532:65532 /source/backend/metadata_writer/src /kfp/metadata_writer
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1
USER 65532:65532
ENTRYPOINT ["/venv/bin/python", "-u", "/kfp/metadata_writer/metadata_writer.py"]
