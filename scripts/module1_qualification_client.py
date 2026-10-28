"""Validate and create the restricted qualification client in dependency order."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

Runner = Callable[..., subprocess.CompletedProcess[str]]
NAMESPACE = "cogniflow-qualification"
NAME = "qualification-client"


def load_resource(path: Path, kind: str) -> dict[str, Any]:
    documents = [item for item in yaml.safe_load_all(path.read_text()) if isinstance(item, dict)]
    if len(documents) != 1 or documents[0].get("kind") != kind:
        raise ValueError(f"{path} must contain exactly one {kind}")
    resource = documents[0]
    metadata = resource.get("metadata", {})
    if metadata.get("name") != NAME or metadata.get("namespace") != NAMESPACE:
        raise ValueError(f"{kind} must be {NAMESPACE}/{NAME}")
    return resource


def validate(service_account_path: Path, pod_path: Path) -> None:
    service_account = load_resource(service_account_path, "ServiceAccount")
    pod = load_resource(pod_path, "Pod")
    if service_account.get("automountServiceAccountToken") is not False:
        raise ValueError("qualification ServiceAccount must disable token automount")
    if pod.get("spec", {}).get("serviceAccountName") != NAME:
        raise ValueError("qualification Pod must use the dedicated ServiceAccount")
    if pod.get("spec", {}).get("automountServiceAccountToken") is not False:
        raise ValueError("qualification Pod must disable token automount")


def apply_client(
    *, context: str, service_account_path: Path, pod_path: Path,
    runner: Runner = subprocess.run,
) -> None:
    validate(service_account_path, pod_path)
    kubectl = ["kubectl", "--context", context]
    runner([*kubectl, "apply", "-f", str(service_account_path)], check=True)
    result = runner(
        [*kubectl, "get", "serviceaccount", NAME, "-n", NAMESPACE, "-o", "json"],
        check=True, text=True, capture_output=True,
    )
    live = json.loads(result.stdout)
    if live.get("metadata", {}).get("namespace") != NAMESPACE or live.get(
        "automountServiceAccountToken"
    ) is not False:
        raise RuntimeError("dedicated qualification ServiceAccount was not verified")
    runner([*kubectl, "apply", "--dry-run=server", "-f", str(pod_path)], check=True)
    runner([*kubectl, "apply", "-f", str(pod_path)], check=True)
    runner(
        [*kubectl, "wait", "--for=condition=Ready", f"pod/{NAME}", "-n", NAMESPACE,
         "--timeout=120s"],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--context", required=True)
    parser.add_argument("--service-account", type=Path, required=True)
    parser.add_argument("--pod", type=Path, required=True)
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("qualification client apply requires explicit --execute authorization")
    apply_client(
        context=args.context,
        service_account_path=args.service_account,
        pod_path=args.pod,
    )


if __name__ == "__main__":
    main()
