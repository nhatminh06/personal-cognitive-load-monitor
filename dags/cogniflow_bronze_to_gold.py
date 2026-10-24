"""Resource-conscious local batch orchestration through existing Compose containers."""

from __future__ import annotations

from datetime import datetime, timedelta

import docker
from airflow import DAG
from airflow.operators.python import PythonOperator


def service(name: str):
    matches = docker.from_env().containers.list(
        filters={"label": f"com.docker.compose.service={name}"}
    )
    if len(matches) != 1:
        raise RuntimeError(f"Expected one running {name} container, found {len(matches)}")
    return matches[0]


def execute(name: str, command: list[str]) -> None:
    result = service(name).exec_run(command, environment={"DBT_PROFILES_DIR": "/analytics", "DBT_TARGET_PATH": "/tmp/dbt-target", "DBT_LOG_PATH": "/tmp/dbt-logs"})
    if result.exit_code:
        raise RuntimeError(result.output.decode("utf-8", errors="replace")[-4000:])


def check_service(name: str) -> None:
    service(name)


def trino(sql: str) -> None:
    execute("trino", ["trino", "--execute", sql])


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
    source = PythonOperator(task_id="check_source", python_callable=check_service, op_args=["minio"])
    validate = PythonOperator(
        task_id="validate_input", python_callable=trino,
        op_args=["SELECT count(*) FROM lakehouse.silver.session_features"],
    )
    spark = PythonOperator(
        task_id="spark_bronze_to_silver", python_callable=execute,
        op_args=["spark", ["/opt/spark/bin/spark-submit", "--packages", "io.delta:delta-spark_2.12:3.3.2,org.apache.hadoop:hadoop-aws:3.3.4", "jobs/bronze_to_silver.py"]],
    )
    silver = PythonOperator(
        task_id="verify_silver", python_callable=trino,
        op_args=["SELECT count(*) FROM lakehouse.silver.session_features"],
    )
    build = PythonOperator(task_id="dbt_build", python_callable=execute, op_args=["dbt-runner", ["dbt", "build"]])
    quality = PythonOperator(
        task_id="verify_gold_quality", python_callable=trino,
        op_args=["SELECT accepted_rows, stale_rows FROM lakehouse.gold.gold_data_quality_summary"],
    )
    source >> validate >> spark >> silver >> build >> quality
