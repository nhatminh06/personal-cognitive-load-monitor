"""Exercise DAG functions without installing Airflow in the application environment."""

import importlib.util
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace

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


@pytest.mark.parametrize("valid,rejected,status", [([{}], [], 200), ([], [], 502), ([{}], [{}], 502)])
def test_runner_bronze_validation_releases_lock(monkeypatch, valid, rejected, status):
    from jobs.internal_job_runner import Handler, _job_lock

    monkeypatch.setitem(sys.modules, "bronze_to_silver", SimpleNamespace(
        load_bronze_accounted=lambda: (valid, rejected, {"bronze_rows_read": len(valid) + len(rejected)}),
    ))
    monkeypatch.setenv("JOB_KIND", "spark")
    monkeypatch.setenv("JOB_RUNNER_TOKEN", "fixture")
    handler = object.__new__(Handler)
    handler.path = "/validate"
    handler.headers = {"Authorization": "Bearer fixture"}
    replies = []
    handler._reply = lambda code, payload: replies.append((code, payload))
    handler.do_POST()
    assert replies[0][0] == status
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
