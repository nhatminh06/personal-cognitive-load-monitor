from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "infra/module2/docker-compose.yml"


def test_spark_is_local_profile_only_and_not_in_helm() -> None:
    config = yaml.safe_load(COMPOSE.read_text())
    spark = config["services"]["spark"]

    assert spark["profiles"] == ["batch"]
    assert "ports" not in spark
    assert spark.get("privileged", False) is False
    assert spark["user"] == "185:185"
    assert spark["read_only"] is True
    assert set(spark["networks"]) == {"spark-storage", "spark-control"}
    assert all(config["networks"][name]["internal"] for name in spark["networks"])
    assert not any("docker.sock" in str(volume) for volume in spark["volumes"])

    helm_text = "\n".join(
        path.read_text() for path in (ROOT / "helm").rglob("*") if path.is_file()
    )
    assert "spark" not in helm_text.lower()


def test_spark_is_bounded_and_offline_cache_is_read_only() -> None:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    spark = services["spark"]

    assert spark["mem_limit"] == "1792m"
    assert spark["cpus"] == 1.5
    assert any(volume.endswith(":/home/spark/.ivy2:ro") for volume in spark["volumes"])
    for service in ("spark", "dbt-runner", "airflow"):
        assert services[service]["environment"]["JOB_RUNNER_TOKEN"] == "${JOB_RUNNER_TOKEN:-}"
