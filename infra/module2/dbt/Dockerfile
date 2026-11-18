FROM python:3.11.18-alpine3.24@sha256:7fbad8e4652eae0186429a6f26cf5b23e27e8c6fd7ac4d0cfd7a6988cdeea1e1

RUN apk upgrade --no-cache \
    && apk add --no-cache --virtual .build-deps build-base \
    && pip install --no-cache-dir \
        dbt-core==1.11.14 \
        dbt-trino==1.10.6 \
        sqlparse==0.6.0 \
    && pip check \
    && python -m pip uninstall -y pip setuptools wheel \
    && apk del .build-deps

RUN adduser -D -u 10001 dbt
USER dbt

ENTRYPOINT ["dbt"]
