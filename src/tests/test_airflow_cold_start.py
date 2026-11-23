"""Exercise DAG functions without installing Airflow in the application environment."""

import importlib.util
import sys
from contextlib import nullcontext
from datetime import timedelta
from pathlib import Path
from types import ModuleType

import pytest


def test_cold_start_validates_bronze_before_creating_silver(monkeypatch):
    edges = []

    class Task:
        def __init__(self, function):
            self.function = function

        def __call__(self):
            return self

        def __rshift__(self, other):
            edges.append((self.function.__name__, other.function.__name__))
            return other

    sdk = ModuleType("airflow.sdk")
    sdk.DAG = lambda *args, **kwargs: nullcontext()
    sdk.task = Task
    monkeypatch.setitem(sys.modules, "airflow", ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    spec = importlib.util.spec_from_file_location("cold_start_dag", Path("dags/cogniflow_bronze_to_gold.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    monkeypatch.setenv("JOB_RUNNER_TOKEN", "fixture")
    monkeypatch.setattr(module, "request", lambda url, **kwargs: calls.append(url))
    module.check_source.function()
    module.validate_input.function()
    module.spark_bronze_to_silver.function()
    assert calls == ["http://spark:8090/health", "http://spark:8090/validate", "http://spark:8090/run"]
    assert len(edges) == 5
    assert edges[:2] == [("check_source", "validate_input"), ("validate_input", "spark_bronze_to_silver")]
    assert edges == list(zip(
        ("check_source", "validate_input", "spark_bronze_to_silver", "verify_silver", "dbt_build"),
        ("validate_input", "spark_bronze_to_silver", "verify_silver", "dbt_build", "verify_gold_quality"),
    ))
    assert module.default_args == {"retries": 2, "retry_delay": timedelta(seconds=10)}

    statements = []
    monkeypatch.setattr(module, "trino", lambda sql: statements.append(sql) or [])
    module.verify_silver.function()
    assert any("CREATE SCHEMA IF NOT EXISTS" in sql for sql in statements)
    assert any("register_table" in sql for sql in statements)
    assert statements[-1] == "SELECT count(*) FROM lakehouse.silver.session_features"


def test_blocked_runner_validation_releases_lock(monkeypatch):
    from jobs.internal_job_runner import Handler, _job_lock

    monkeypatch.setenv("JOB_KIND", "spark")
    monkeypatch.setenv("JOB_RUNNER_TOKEN", "fixture")
    handler = object.__new__(Handler)
    handler.path = "/validate"
    handler.headers = {"Authorization": "Bearer fixture"}
    replies = []
    handler._reply = lambda code, payload: replies.append((code, payload))
    handler.do_POST()
    assert replies == [(502, {"detail": "Spark runtime is security blocked"})]
    assert not _job_lock.locked()


def test_bronze_validation_requires_credentials(monkeypatch):
    from jobs.internal_job_runner import Handler

    monkeypatch.setenv("JOB_RUNNER_TOKEN", "fixture")
    handler = object.__new__(Handler)
    handler.path = "/validate"
    handler.headers = {}
    replies = []
    handler._reply = lambda code, payload: replies.append(code)
    handler.do_POST()
    assert replies == [401]


def test_dag_runner_credentials_and_retryable_failures(monkeypatch):
    sdk = ModuleType("airflow.sdk")
    sdk.DAG = lambda *args, **kwargs: nullcontext()
    class Task:
        def __init__(self, function):
            self.function = function

        def __call__(self):
            return self

        def __rshift__(self, other):
            return other

    sdk.task = Task
    monkeypatch.setitem(sys.modules, "airflow", ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    spec = importlib.util.spec_from_file_location("offline_dag", Path("dags/cogniflow_bronze_to_gold.py"))
    dag_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dag_module)

    calls = []
    monkeypatch.delenv("JOB_RUNNER_TOKEN", raising=False)
    monkeypatch.setattr(dag_module, "request", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(RuntimeError, match="not configured"):
        dag_module.run_allowlisted_job("dbt-runner")
    assert calls == []

    monkeypatch.setenv("JOB_RUNNER_TOKEN", "fixture")
    attempts = []

    def transient(url, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            raise RuntimeError("HTTP 500")

    monkeypatch.setattr(dag_module, "request", transient)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        dag_module.run_allowlisted_job("dbt-runner")
    dag_module.run_allowlisted_job("dbt-runner")
    assert attempts == ["http://dbt-runner:8090/run"] * 2

    monkeypatch.setattr(dag_module, "request", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("HTTP 500")))
    for _ in range(dag_module.default_args["retries"] + 1):
        with pytest.raises(RuntimeError, match="HTTP 500"):
            dag_module.run_allowlisted_job("dbt-runner")
