FROM python:3.11-slim

RUN pip install --no-cache-dir \
        dbt-core==1.11.14 \
        dbt-trino==1.10.6 \
        sqlparse==0.6.0 \
    && pip check \
    && python -m pip uninstall -y pip setuptools wheel

RUN useradd --create-home --uid 10001 dbt
USER dbt

ENTRYPOINT ["dbt"]
