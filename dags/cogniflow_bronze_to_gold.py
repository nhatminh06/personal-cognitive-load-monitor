"""Resource-conscious local batch orchestration without Docker daemon access."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from airflow.sdk import DAG, task

TIMEOUT_SECONDS = 30
RUNNER_TIMEOUT_SECONDS = 1810


def request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = TIMEOUT_SECONDS,
) -> bytes:
    try:
        with urlopen(Request(url, data=data, headers=headers or {}), timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Request to {url} failed: HTTP {exc.code}: {detail}") from exc


def run_allowlisted_job(service: str, action: str = "run") -> None:
    if service not in {"spark", "dbt-runner"}:
        raise ValueError(f"Unsupported runner: {service}")
    if action not in {"run", "validate"} or (action == "validate" and service != "spark"):
        raise ValueError(f"Unsupported runner action: {action}")
    token = os.environ.get("JOB_RUNNER_TOKEN", "")
    if not token.strip():
        raise RuntimeError("JOB_RUNNER_TOKEN is not configured")
    request(
        f"http://{service}:8090/{action}",
        data=b"",
        headers={"Authorization": f"Bearer {token}"},
        timeout=RUNNER_TIMEOUT_SECONDS,
    )


def trino(sql: str) -> list[list[object]]:
    url = "http://trino:8080/v1/statement"
    payload = json.loads(request(url, data=sql.encode(), headers={"X-Trino-User": "airflow"}))
    rows = payload.get("data", [])
    while "nextUri" in payload:
        payload = json.loads(request(payload["nextUri"], headers={"X-Trino-User": "airflow"}))
        rows.extend(payload.get("data", []))
    if "error" in payload:
        raise RuntimeError(payload["error"].get("message", "Trino query failed"))
    return rows


default_args = {"retries": 2, "retry_delay": timedelta(seconds=10)}
with DAG(
    "cogniflow_bronze_to_gold",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args=default_args,
    max_active_runs=1,
    tags=["cogniflow", "module2"],
) as dag:

    @task
    def check_source() -> None:
        request("http://spark:8090/health")

    @task
    def validate_input() -> None:
        run_allowlisted_job("spark", "validate")

    @task
    def spark_bronze_to_silver() -> None:
        run_allowlisted_job("spark")

    @task
    def verify_silver() -> None:
        trino(
            "CREATE SCHEMA IF NOT EXISTS lakehouse.silver "
            "WITH (location = 's3://cogniflow-lakehouse/metastore/silver')"
        )
        registered = trino(
            "SELECT table_name FROM lakehouse.information_schema.tables "
            "WHERE table_schema = 'silver' AND table_name = 'session_features'"
        )
        if not registered:
            trino(
                "CALL lakehouse.system.register_table("
                "schema_name => 'silver', table_name => 'session_features', "
                "table_location => 's3://cogniflow-lakehouse/silver/session_features')"
            )
        trino("SELECT count(*) FROM lakehouse.silver.session_features")

    @task
    def dbt_build() -> None:
        run_allowlisted_job("dbt-runner")

    @task
    def verify_gold_quality() -> None:
        trino(
            "SELECT accepted_rows, stale_rows "
            "FROM lakehouse.gold.gold_data_quality_summary"
        )

    check_source() >> validate_input() >> spark_bronze_to_silver() >> verify_silver() >> dbt_build() >> verify_gold_quality()
