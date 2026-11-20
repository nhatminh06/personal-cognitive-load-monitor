from __future__ import annotations

from pathlib import Path
import os
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "deploy/c18/mysql/Dockerfile"
INITIALIZER = ROOT / "deploy/c18/mysql/init-kfp-databases.sql"
GRANTS = ROOT / "deploy/c18/mysql/grant-kfp-databases.sh"


def test_minimal_mysql_image_is_pinned_non_root_and_contains_no_shell_tooling() -> None:
    text = DOCKERFILE.read_text()
    assert "oraclelinux@sha256:" in text
    assert "mysql-community-server-minimal-${MYSQL_VERSION}" in text
    assert "rpm -V mysql-community-server-minimal" in text
    assert "USER mysql:mysql" in text
    assert "mysql-shell" not in text
    assert "gosu" not in text
    assert "pip " not in text


def test_kfp_database_initializer_creates_exact_required_databases() -> None:
    text = INITIALIZER.read_text()
    assert [line.removeprefix("CREATE DATABASE IF NOT EXISTS ").removesuffix(";")
            for line in text.splitlines() if line.startswith("CREATE DATABASE")] == [
        "mlpipeline", "cachedb", "metadb",
    ]


def test_initializer_grants_runtime_user_only_required_additional_schemas() -> None:
    command = "set -e; docker_process_sql() { cat; }; mysql_error() { return 1; }; source \"$1\""
    environment = {**os.environ, "MYSQL_USER": "fixture_app", "MYSQL_PASSWORD": "fixture-only"}
    result = subprocess.run(
        ["bash", "-c", command, "bash", str(GRANTS)],
        env=environment, capture_output=True, text=True, check=True,
    )
    assert result.stdout.splitlines() == [
        "    GRANT ALL PRIVILEGES ON `mlpipeline`.* TO 'fixture_app'@'%';",
        "    GRANT ALL PRIVILEGES ON `cachedb`.* TO 'fixture_app'@'%';",
    ]
    assert "*.*" not in result.stdout
    environment.pop("MYSQL_USER")
    missing = subprocess.run(
        ["bash", "-c", command, "bash", str(GRANTS)],
        env=environment, capture_output=True, text=True,
    )
    assert missing.returncode != 0
