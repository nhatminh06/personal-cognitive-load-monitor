"""Read-only target checks before any authorized GKE release action."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from scripts.c11_runtime_preflight import (
    PROTECTED_CLUSTERS,
    controller_matrix_qualified,
    validate_image_ledger,
)


def assess(
    *, project: str, region: str, cluster: str, context: str,
    kubeconfig: Path, controller_matrix: Path, image_ledger: Path,
) -> dict[str, object]:
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("explicit GCP project ID is required")
    if not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", region):
        raise ValueError("explicit GCP region is required")
    if not cluster or cluster in PROTECTED_CLUSTERS or context.startswith("kind-"):
        raise ValueError("protected or invalid GKE target")
    if not kubeconfig.is_file() or kubeconfig.is_symlink():
        raise ValueError("explicit regular kubeconfig is required")
    if not controller_matrix_qualified(controller_matrix):
        raise ValueError("controller compatibility matrix is not qualified")
    validate_image_ledger(image_ledger)

    def run(*command: str) -> str:
        return subprocess.run(command, check=True, text=True, capture_output=True).stdout

    description = json.loads(run(
        "gcloud", "container", "clusters", "describe", cluster,
        "--project", project, "--region", region, "--format=json",
    ))
    if (
        description.get("name") != cluster
        or description.get("location") != region
        or description.get("status") != "RUNNING"
        or not str(description.get("currentMasterVersion", "")).startswith("1.35.")
        or description.get("workloadIdentityConfig", {}).get("workloadPool")
        != f"{project}.svc.id.goog"
    ):
        raise ValueError("GKE cluster identity or readiness mismatch")
    kubectl = ("kubectl", "--kubeconfig", str(kubeconfig), "--context", context)
    config = json.loads(run(*kubectl, "config", "view", "--minify", "-o", "json"))
    endpoints = [item.get("cluster", {}).get("server") for item in config.get("clusters", [])]
    if (
        config.get("current-context") != context
        or len(endpoints) != 1
        or endpoints[0] != f"https://{description.get('endpoint')}"
    ):
        raise ValueError("kubeconfig context mismatch")
    nodes = json.loads(run(*kubectl, "get", "nodes", "-o", "json"))["items"]
    if len(nodes) < 2 or any(
        not any(c.get("type") == "Ready" and c.get("status") == "True"
                for c in node.get("status", {}).get("conditions", []))
        or "cpu" not in node.get("status", {}).get("allocatable", {})
        or "memory" not in node.get("status", {}).get("allocatable", {})
        for node in nodes
    ):
        raise ValueError("GKE nodes are not ready or allocatable is unavailable")
    return {
        "status": "PASS_TARGET_IDENTITY_ONLY",
        "project": project,
        "region": region,
        "cluster": cluster,
        "context": context,
        "control_plane_version": description["currentMasterVersion"],
        "node_allocatable": [node["status"]["allocatable"] for node in nodes],
        "qualification_note": "Target identity is verified; image signatures, scans, storage, Secrets and workload schedulability still require release acceptance.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("project", "region", "cluster", "context"):
        parser.add_argument(f"--{name}", required=True)
    for name in ("kubeconfig", "controller-matrix", "image-ledger"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(assess(**vars(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
