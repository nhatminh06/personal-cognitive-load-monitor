"""Fail-closed host checks before creating the disposable Module I cluster."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

GIB = 1024**3
MIN_AVAILABLE_MEMORY = 10 * GIB
MIN_CPUS = 4
MIN_DISK = 30 * GIB
MAX_QUALIFICATION_BUDGET = 16 * GIB
EXPECTED_PEAK_MEMORY = 12 * GIB


def validate_resources(
    *, memory: int, cpus: int, disk: int, docker_memory: int, docker_cpus: int, docker_disk: int
) -> None:
    if EXPECTED_PEAK_MEMORY > MAX_QUALIFICATION_BUDGET:
        raise RuntimeError("qualification exceeds the 16 GiB local RAM budget")
    if memory < MIN_AVAILABLE_MEMORY or docker_memory < MIN_AVAILABLE_MEMORY:
        raise RuntimeError("at least 10 GiB available host and Docker memory is required")
    if cpus < MIN_CPUS or docker_cpus < MIN_CPUS:
        raise RuntimeError("at least 4 CPUs are required")
    if disk < MIN_DISK or docker_disk < MIN_DISK:
        raise RuntimeError("at least 30 GiB free disk is required")


def available_memory() -> int:
    values = {
        key.rstrip(":"): int(value) * 1024
        for key, value, *_ in (line.split() for line in Path("/proc/meminfo").read_text().splitlines())
    }
    return values["MemAvailable"]


def output(*command: str) -> str:
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--cluster", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("preflight requires explicit --execute authorization")
    if args.context != f"kind-{args.cluster}":
        raise SystemExit("context must be the unique kind context for the requested cluster")
    for command in ("docker", "git", "kind", "kubectl", "kustomize", "sha256sum"):
        if shutil.which(command) is None:
            raise SystemExit(f"required command is unavailable: {command}")
    clusters = set(output("kind", "get", "clusters").splitlines())
    contexts = set(output("kubectl", "config", "get-contexts", "-o", "name").splitlines())
    if args.cluster in clusters or args.context in contexts:
        raise SystemExit("qualification cluster or context already exists")
    docker = json.loads(output("docker", "info", "--format", "{{json .}}"))
    validate_resources(
        memory=available_memory(),
        cpus=os.cpu_count() or 0,
        disk=shutil.disk_usage(args.workspace).free,
        docker_memory=int(docker.get("MemTotal", 0)),
        docker_cpus=int(docker.get("NCPU", 0)),
        docker_disk=shutil.disk_usage(str(docker.get("DockerRootDir", "/var/lib/docker"))).free,
    )
    print(json.dumps({"cluster": args.cluster, "context": args.context, "status": "authorized"}))


if __name__ == "__main__":
    main()
