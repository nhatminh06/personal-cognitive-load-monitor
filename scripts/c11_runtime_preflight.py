"""Fail-closed preflight for a separately authorized C11 Kubernetes runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any


PROTECTED_CLUSTERS = {"cogniflow-local", "cogniflow-module1-qualification"}
IMAGE = re.compile(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}")
REQUIRED_IMAGES = {
    "kfp-api", "kfp-persistence-agent", "kfp-scheduled-workflow", "workflow-controller",
    "kserve-controller", "knative-serving-controller", "knative-eventing-controller",
    "eventing-durable-transport", "ingress-controller", "cert-manager", "artifact-store",
    "mlflow", "cogniflow-kfp", "cogniflow-kserve", "cognitive-load-api",
    "event-consumer", "anomaly-detector",
}
REQUIRED_CONTROLLERS = {
    "kubernetes", "kubectl", "kfp-runtime", "kfp-sdk", "kserve", "knative-serving",
    "knative-eventing", "istio", "cert-manager", "artifact-storage", "mlflow",
}
MINIMUM_MEMORY_BYTES = 12 * 1024**3
MINIMUM_DISK_BYTES = 60 * 1024**3


def available_memory() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def validate_target(cluster: str, context: str) -> None:
    if cluster in PROTECTED_CLUSTERS or context in {f"kind-{name}" for name in PROTECTED_CLUSTERS}:
        raise ValueError("protected cluster selected")
    if not re.fullmatch(r"cogniflow-c11-[a-z0-9-]+", cluster):
        raise ValueError("C11 cluster name must use the cogniflow-c11- prefix")
    if context != f"kind-{cluster}":
        raise ValueError("C11 context must exactly match the isolated kind cluster")


def kubectl_command(binary: Path, kubeconfig: Path, context: str, *arguments: str) -> list[str]:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("qualified kubectl is missing")
    if not kubeconfig.is_file() or kubeconfig.is_symlink():
        raise ValueError("explicit C11 kubeconfig is missing or unsafe")
    return [str(binary), "--kubeconfig", str(kubeconfig), "--context", context, *arguments]


def validate_image_ledger(path: Path) -> None:
    ledger = json.loads(path.read_text())
    if not isinstance(ledger, dict) or set(ledger) != REQUIRED_IMAGES:
        raise ValueError("image qualification ledger is incomplete")
    for name, item in ledger.items():
        if (
            not isinstance(item, dict)
            or not IMAGE.fullmatch(str(item.get("reference", "")))
            or item.get("signature_verified") is not True
            or item.get("scan") != {"complete": True, "high": 0, "critical": 0}
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sbom_sha256", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("provenance_sha256", "")))
        ):
            raise ValueError(f"image qualification is incomplete for {name}")


def controller_matrix_qualified(path: Path) -> bool:
    try:
        matrix = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    components = matrix.get("components") if isinstance(matrix, dict) else None
    return (
        isinstance(components, dict)
        and set(components) == REQUIRED_CONTROLLERS
        and all(
            isinstance(item, dict)
            and item.get("qualified") is True
            and isinstance(item.get("version"), str)
            and bool(item["version"])
            and isinstance(item.get("source"), str)
            and item["source"].startswith("https://")
            for item in components.values()
        )
    )


def assess(plan_path: Path, output: Path) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text())
    required = {
        "cluster_name", "context", "option", "owner_authorization", "kubeconfig",
        "qualified_kubectl", "image_ledger", "controller_matrix", "storage_qualified",
        "minimum_available_memory_bytes", "minimum_disk_bytes",
    }
    if not isinstance(plan, dict) or set(plan) != required:
        raise ValueError("C11 preflight plan schema is invalid")
    validate_target(str(plan["cluster_name"]), str(plan["context"]))
    if plan["option"] not in {"existing_independent", "dedicated_kind"}:
        raise ValueError("C11 execution option is invalid")
    if int(plan["minimum_available_memory_bytes"]) < MINIMUM_MEMORY_BYTES:
        raise ValueError("C11 memory requirement cannot be below 12 GiB")
    if int(plan["minimum_disk_bytes"]) < MINIMUM_DISK_BYTES:
        raise ValueError("C11 disk requirement cannot be below 60 GiB")

    memory = available_memory()
    disk = shutil.disk_usage("/").free
    gates = {
        "owner_authorization": plan["owner_authorization"] is True,
        "memory": memory >= int(plan["minimum_available_memory_bytes"]),
        "disk": disk >= int(plan["minimum_disk_bytes"]),
        "controller_matrix": bool(plan["controller_matrix"]) and controller_matrix_qualified(
            Path(str(plan["controller_matrix"]))
        ),
        "storage": plan["storage_qualified"] is True,
        "images": bool(plan["image_ledger"]),
        "kubeconfig": Path(str(plan["kubeconfig"])).is_file(),
        "kubectl": Path(str(plan["qualified_kubectl"])).is_file(),
    }
    if gates["images"]:
        validate_image_ledger(Path(str(plan["image_ledger"])))
    if gates["kubeconfig"] and gates["kubectl"]:
        kubectl_command(
            Path(str(plan["qualified_kubectl"])), Path(str(plan["kubeconfig"])),
            str(plan["context"]), "get", "nodes",
        )
    blockers = [name for name, passed in gates.items() if not passed]
    result = {
        "schema_version": "1.0",
        "status": "PASS" if not blockers else "BLOCKED",
        "selected_option": plan["option"],
        "cluster_name": plan["cluster_name"],
        "context": plan["context"],
        "protected_clusters": sorted(PROTECTED_CLUSTERS),
        "measurements": {"available_memory_bytes": memory, "available_disk_bytes": disk},
        "requirements": {
            "available_memory_bytes": int(plan["minimum_available_memory_bytes"]),
            "available_disk_bytes": int(plan["minimum_disk_bytes"]),
        },
        "gates": gates,
        "blockers": blockers,
        "mutation_executed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = assess(args.plan.resolve(), args.output.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
