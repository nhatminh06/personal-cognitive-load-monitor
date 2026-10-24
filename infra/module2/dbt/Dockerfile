FROM python:3.11-slim

RUN pip install --no-cache-dir dbt-core==1.10.15 dbt-trino==1.10.3 \
    && python -m pip uninstall -y pip setuptools

RUN useradd --create-home --uid 10001 dbt
USER dbt

ENTRYPOINT ["dbt"]
