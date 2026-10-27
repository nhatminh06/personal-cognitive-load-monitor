"""Fail-closed preflight and evidence bootstrap for an isolated Module II rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "infra/module2/docker-compose.yml"
OVERRIDE = ROOT / "infra/module2/docker-compose.rehearsal.yml"
SEC022 = ROOT / "docs/security-audit/sec-022-development-exception-proposal.md"
IVY_MANIFEST = ROOT / "infra/module2/spark/ivy-manifest.sha256"
SPARK_IMAGE = "cogniflow-spark:3.5.5-delta-3.3.2"
SPARK_IMAGE_ID = "sha256:d55eac37429cb0d94208d79fcae0f1002662b1d9700eb1b4a522bbe6cf2bb0e8"
MIN_AVAILABLE_BYTES = 6 * 1024**3
MIN_DISK_BYTES = 10 * 1024**3
PROJECT_PATTERN = re.compile(r"^cogniflow-rehearsal-[a-z0-9-]+$")


@dataclass(frozen=True)
class Ports:
    kafka: int
    s3: int
    trino: int
    redis: int
    flink: int


def available_memory() -> int:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.split()[0]) * 1024
    return values["MemAvailable"]


def choose_ports(count: int = 5) -> list[int]:
    sockets = []
    try:
        for _ in range(count):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            sockets.append(listener)
        return [listener.getsockname()[1] for listener in sockets]
    finally:
        for listener in sockets:
            listener.close()


def validate_project(project: str) -> None:
    if not PROJECT_PATTERN.fullmatch(project) or project == "cogniflow-module2":
        raise ValueError("project must be a unique cogniflow-rehearsal-* name")


def validate_resources(memory: int, disk: int) -> None:
    if memory < MIN_AVAILABLE_BYTES:
        raise RuntimeError("at least 6 GiB available RAM is required")
    if disk < MIN_DISK_BYTES:
        raise RuntimeError("at least 10 GiB free disk is required")


def validate_isolation(
    project: str,
    ports: Ports,
    containers: list[dict[str, Any]],
    networks: list[dict[str, Any]],
) -> None:
    validate_project(project)
    if any(container.get("Labels", {}).get("com.docker.compose.project") == project for container in containers):
        raise RuntimeError(f"Compose project already exists: {project}")
    names = {network["Name"] for network in networks}
    if f"{project}-default" in names or any(name.startswith(f"{project}_") for name in names):
        raise RuntimeError(f"Docker network already exists for {project}")
    requested = {ports.kafka, ports.s3, ports.trino, ports.redis, ports.flink}
    if len(requested) != 5:
        raise RuntimeError("rehearsal host ports must be unique")
    occupied = {
        int(binding["HostPort"])
        for container in containers
        for bindings in (container.get("NetworkSettings", {}).get("Ports") or {}).values()
        for binding in bindings or []
        if binding.get("HostIp") in {"0.0.0.0", "127.0.0.1", "::"}
    }
    collisions = sorted(requested & occupied)
    if collisions:
        raise RuntimeError(f"rehearsal host ports are occupied: {collisions}")


def validate_sec022(today: date, image_id: str, exception_text: str) -> None:
    if today > date(2027, 1, 23):
        raise RuntimeError("SEC-022 development exception is expired")
    if "ACCEPTED RISK — LOCAL DEVELOPMENT ONLY" not in exception_text:
        raise RuntimeError("SEC-022 acceptance record is missing")
    if image_id != SPARK_IMAGE_ID:
        raise RuntimeError("Spark image ID does not match the SEC-022 approval")


def redact(text: str, secret_values: list[str]) -> str:
    for value in sorted((value for value in secret_values if value), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text


class Evidence:
    def __init__(self, directory: Path, secrets_to_redact: list[str]) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=False)
        self.secrets = secrets_to_redact
        self.records: list[dict[str, Any]] = []

    def record(self, name: str, command: list[str], result: subprocess.CompletedProcess[str]) -> None:
        path = self.directory / f"{len(self.records) + 1:02d}-{name}.txt"
        output = redact(result.stdout + result.stderr, self.secrets)
        path.write_text(output)
        self.records.append(
            {
                "name": name,
                "command": command,
                "exit_code": result.returncode,
                "timestamp": datetime.now(UTC).isoformat(),
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    def finish(self, summary: dict[str, Any]) -> None:
        payload = {**summary, "commands": self.records}
        (self.directory / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        lines = ["# Module II isolated rehearsal", ""]
        lines.extend(f"- {key.replace('_', ' ').title()}: {value}" for key, value in summary.items())
        lines.extend(["", "## Captured commands", ""])
        lines.extend(f"- `{item['name']}`: exit {item['exit_code']}, `{item['file']}`" for item in self.records)
        (self.directory / "report.md").write_text("\n".join(lines) + "\n")


def run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False)


def docker_json(command: list[str]) -> list[dict[str, Any]]:
    result = run(command)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Docker inspection failed")
    return json.loads(result.stdout)


def docker_json_lines(command: list[str]) -> list[dict[str, Any]]:
    result = run(command)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Docker inspection failed")
    return [json.loads(line) for line in result.stdout.splitlines() if line]


def validate_resolved_config(config: dict[str, Any], project: str, ports: Ports) -> None:
    if config.get("name") != project:
        raise RuntimeError("resolved Compose project name is not isolated")
    if config["networks"]["default"].get("name") != f"{project}-default":
        raise RuntimeError("resolved default network name is not isolated")
    expected = {
        "kafka": ports.kafka,
        "minio": ports.s3,
        "trino": ports.trino,
        "redis": ports.redis,
        "flink-jobmanager": ports.flink,
    }
    for service, published in expected.items():
        mappings = config["services"][service].get("ports", [])
        if len(mappings) != 1 or mappings[0].get("host_ip") != "127.0.0.1" or int(mappings[0]["published"]) != published:
            raise RuntimeError(f"resolved host-port isolation failed for {service}")
    spark = config["services"]["spark"]
    if spark.get("ports") or spark.get("read_only") is not True or spark.get("user") != "185:185":
        raise RuntimeError("resolved Spark isolation controls are incomplete")
    if not config["services"]["flink-taskmanager"].get("environment", {}).get("REDIS_PASSWORD"):
        raise RuntimeError("resolved Flink TaskManager credential is missing")
    if any(not details.get("internal") for name, details in config["networks"].items() if name in {"spark-storage", "spark-control"}):
        raise RuntimeError("resolved Spark networks must be internal")
    if any(not details.get("name", "").startswith(f"{project}_") for details in config["volumes"].values()):
        raise RuntimeError("resolved volumes are not owned by the rehearsal project")


def compose_command(profiles: list[str], *args: str) -> list[str]:
    command = ["docker", "compose", "-f", str(COMPOSE), "-f", str(OVERRIDE)]
    for profile in profiles:
        command.extend(["--profile", profile])
    return [*command, *args]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate isolation and create an evidence directory; runtime phases remain explicit."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--project")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    project = args.project or f"cogniflow-rehearsal-{stamp.lower()}"
    validate_project(project)
    selected = choose_ports()
    ports = Ports(*selected)
    container_ids = run(["docker", "ps", "-aq"]).stdout.split()
    containers = docker_json(["docker", "inspect", *container_ids]) if container_ids else []
    networks = docker_json_lines(["docker", "network", "ls", "--format", "{{json .}}"])
    validate_resources(available_memory(), shutil.disk_usage(ROOT).free)
    validate_isolation(project, ports, containers, networks)

    image = docker_json(["docker", "image", "inspect", SPARK_IMAGE])
    validate_sec022(date.today(), image[0]["Id"], SEC022.read_text())
    env = os.environ.copy()
    env.update(
        {
            "REHEARSAL_PROJECT": project,
            "REHEARSAL_KAFKA_PORT": str(ports.kafka),
            "REHEARSAL_S3_PORT": str(ports.s3),
            "REHEARSAL_TRINO_PORT": str(ports.trino),
            "REHEARSAL_REDIS_PORT": str(ports.redis),
            "REHEARSAL_FLINK_PORT": str(ports.flink),
            "MINIO_ROOT_USER": f"rehearsal-{secrets.token_hex(8)}",
            "MINIO_ROOT_PASSWORD": secrets.token_urlsafe(32),
            "REDIS_PASSWORD": secrets.token_urlsafe(32),
            "JOB_RUNNER_TOKEN": secrets.token_urlsafe(32),
            "COGNIFLOW_API_KEY": secrets.token_urlsafe(32),
            "MINIO_BRONZE_BUCKET": "cogniflow-bronze",
            "MINIO_LAKEHOUSE_BUCKET": "cogniflow-lakehouse",
        }
    )
    resolved_command = compose_command(["ingestion", "lake", "batch", "analytics", "streaming", "orchestration", "orchestration-dev"], "config", "--format", "json")
    resolved = run(resolved_command, env=env)
    if resolved.returncode:
        raise RuntimeError(resolved.stderr.strip())
    validate_resolved_config(json.loads(resolved.stdout), project, ports)
    if not args.execute:
        print(json.dumps({"status": "dry-run", "project": project, "ports": asdict(ports), "sec022": "passed"}, sort_keys=True))
        return

    run_dir = (args.run_dir or ROOT / "build/module2-rehearsal" / project).resolve()
    secret_file = run_dir / ".env.secrets"
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    secret_keys = (
        "REHEARSAL_PROJECT", "REHEARSAL_KAFKA_PORT", "REHEARSAL_S3_PORT",
        "REHEARSAL_TRINO_PORT", "REHEARSAL_REDIS_PORT", "REHEARSAL_FLINK_PORT",
        "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "MINIO_BRONZE_BUCKET",
        "MINIO_LAKEHOUSE_BUCKET", "REDIS_PASSWORD", "JOB_RUNNER_TOKEN",
        "COGNIFLOW_API_KEY",
    )
    evidence = Evidence(
        run_dir,
        [env[key] for key in ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "REDIS_PASSWORD", "JOB_RUNNER_TOKEN", "COGNIFLOW_API_KEY")],
    )
    secret_file.write_text("\n".join(f"{key}={env[key]}" for key in secret_keys) + "\n")
    secret_file.chmod(0o600)
    config_result = subprocess.CompletedProcess(resolved.args, resolved.returncode, redact(resolved.stdout, evidence.secrets), redact(resolved.stderr, evidence.secrets))
    evidence.record("compose-config", resolved_command, config_result)
    evidence.finish(
        {
            "status": "preflight-passed",
            "git_commit": run(["git", "rev-parse", "HEAD"]).stdout.strip(),
            "project": project,
            "ports": asdict(ports),
            "sec022": "passed",
            "spark_image_id": SPARK_IMAGE_ID,
            "ivy_manifest_sha256": hashlib.sha256(IVY_MANIFEST.read_bytes()).hexdigest(),
            "runtime_executed": False,
            "cleanup_status": "not-started",
        }
    )
    print(json.dumps({"status": "preflight-passed", "project": project, "run_dir": str(run_dir)}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
