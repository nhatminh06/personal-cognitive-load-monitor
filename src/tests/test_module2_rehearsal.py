from __future__ import annotations

import hashlib
import json
import stat
import subprocess
from datetime import date
from pathlib import Path

import pytest

from scripts.module2_e2e_rehearsal import (
    Evidence,
    Ports,
    SPARK_IMAGE_ID,
    create_secret_file,
    validate_isolation,
    validate_project,
    validate_resolved_config,
    validate_resources,
    validate_sec022,
)


PORTS = Ports(31001, 31002, 31003, 31004, 31005)


def resolved_config(project: str = "cogniflow-rehearsal-test") -> dict:
    services = {}
    for service, port in zip(("kafka", "minio", "trino", "redis", "flink-jobmanager"), PORTS.__dict__.values()):
        services[service] = {"ports": [{"host_ip": "127.0.0.1", "published": str(port)}]}
    services["spark"] = {"read_only": True, "user": "185:185"}
    services["flink-taskmanager"] = {"environment": {"REDIS_PASSWORD": "fixture-secret"}}
    return {
        "name": project,
        "services": services,
        "networks": {
            "default": {"name": f"{project}-default"},
            "spark-storage": {"name": f"{project}_spark-storage", "internal": True},
            "spark-control": {"name": f"{project}_spark-control", "internal": True},
        },
        "volumes": {"data": {"name": f"{project}_data"}},
    }


def test_isolation_rejects_project_network_and_port_collisions() -> None:
    project = "cogniflow-rehearsal-test"
    with pytest.raises(RuntimeError, match="project already exists"):
        validate_isolation(project, PORTS, [{"Labels": {"com.docker.compose.project": project}}], [])
    with pytest.raises(RuntimeError, match="network already exists"):
        validate_isolation(project, PORTS, [], [{"Name": f"{project}-default"}])
    container = {"Labels": {}, "NetworkSettings": {"Ports": {"1/tcp": [{"HostIp": "127.0.0.1", "HostPort": "31003"}]}}}
    with pytest.raises(RuntimeError, match="occupied"):
        validate_isolation(project, PORTS, [container], [])


def test_resolved_compose_owns_volumes_and_preserves_spark_isolation() -> None:
    validate_resolved_config(resolved_config(), "cogniflow-rehearsal-test", PORTS)
    invalid = resolved_config()
    invalid["volumes"]["data"]["name"] = "cogniflow-module2_data"
    with pytest.raises(RuntimeError, match="volumes"):
        validate_resolved_config(invalid, "cogniflow-rehearsal-test", PORTS)


def test_preflight_requires_unique_project_and_resource_budget() -> None:
    with pytest.raises(ValueError, match="unique"):
        validate_project("cogniflow-module2")
    with pytest.raises(RuntimeError, match="6 GiB"):
        validate_resources(1, 20 * 1024**3)
    with pytest.raises(RuntimeError, match="10 GiB"):
        validate_resources(20 * 1024**3, 1)


def test_sec022_gate_fails_closed_for_expiry_or_image_drift() -> None:
    acceptance = "ACCEPTED RISK — LOCAL DEVELOPMENT ONLY"
    validate_sec022(date(2026, 10, 27), SPARK_IMAGE_ID, acceptance)
    with pytest.raises(RuntimeError, match="expired"):
        validate_sec022(date(2027, 1, 24), SPARK_IMAGE_ID, acceptance)
    with pytest.raises(RuntimeError, match="image ID"):
        validate_sec022(date(2026, 10, 27), "sha256:wrong", acceptance)


def test_evidence_redacts_secrets_and_hashes_captured_output(tmp_path: Path) -> None:
    evidence = Evidence(tmp_path / "run", ["secret-token"])
    result = subprocess.CompletedProcess(["demo"], 0, "token=secret-token\n", "")
    evidence.record("demo", ["demo"], result)
    evidence.finish({"status": "passed"})
    captured = tmp_path / "run/01-demo.txt"
    summary = json.loads((tmp_path / "run/summary.json").read_text())
    assert captured.read_text() == "token=[REDACTED]\n"
    assert summary["commands"][0]["sha256"] == hashlib.sha256(captured.read_bytes()).hexdigest()


def test_secret_file_is_created_exclusively_with_private_permissions(tmp_path: Path) -> None:
    path = tmp_path / ".env.secrets"
    create_secret_file(path, "TOKEN=secret\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == "TOKEN=secret\n"


def test_secret_file_rejects_existing_path_without_changing_it(tmp_path: Path) -> None:
    path = tmp_path / ".env.secrets"
    path.write_text("preserve-me\n")
    with pytest.raises(FileExistsError):
        create_secret_file(path, "TOKEN=must-not-appear\n")
    assert path.read_text() == "preserve-me\n"


def test_isolated_demo_cannot_target_shared_module2_project() -> None:
    guide = (Path(__file__).parents[2] / "docs/module2/demo-script.md").read_text()
    assert "make module2-" not in guide
    assert "cogniflow-module2" not in guide
    assert guide.count("docker compose") == 1
    assert "-p cogniflow-rehearsal-YYYYMMDDa" in guide
    assert "-f infra/module2/docker-compose.yml" in guide
    assert "-f infra/module2/docker-compose.rehearsal.yml" in guide
