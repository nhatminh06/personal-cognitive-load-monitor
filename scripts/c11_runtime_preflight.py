"""Fail-closed preflight for a separately authorized C11 Kubernetes runtime."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


PROTECTED_CLUSTERS = {"cogniflow-local", "cogniflow-module1-qualification"}
IMAGE = re.compile(r"[a-z0-9./_-]+@sha256:[0-9a-f]{64}")
REQUIRED_IMAGES = {
    "kfp-api", "kfp-persistence-agent", "kfp-scheduled-workflow", "kfp-driver",
    "kfp-launcher", "kfp-metadata-writer", "kfp-metadata-envoy", "ml-metadata",
    "kfp-database", "kfp-init", "workflow-controller", "workflow-executor",
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
    """Validate offline ledger shape only; this does not qualify any image."""
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


def _run(binary: Path, *arguments: str) -> str:
    if not binary.is_file() or not os.access(binary, os.X_OK) or binary.is_symlink():
        raise ValueError(f"qualified tool is missing or unsafe: {binary}")
    try:
        return subprocess.run(
            [str(binary), *arguments], check=True, capture_output=True, text=True
        ).stdout
    except subprocess.CalledProcessError as error:
        raise ValueError(f"qualified tool verification failed: {binary.name}") from error


def _attestation_payload(output: str, reference: str, predicate: str) -> bytes:
    digest = reference.rsplit("@sha256:", 1)[1]
    for line in output.splitlines():
        try:
            envelope = json.loads(line)
            payload = base64.b64decode(envelope["payload"], validate=True)
            statement = json.loads(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        subjects = statement.get("subject", [])
        predicate_type = str(statement.get("predicateType", "")).lower()
        if (
            isinstance(subjects, list)
            and any(
                isinstance(subject, dict)
                and isinstance(subject.get("digest"), dict)
                and subject["digest"].get("sha256") == digest
                for subject in subjects
            )
            and predicate in predicate_type
        ):
            return payload
    raise ValueError(f"missing digest-bound {predicate} attestation for {reference}")


def qualify_image_ledger(
    path: Path,
    cosign: Path,
    cosign_sha256: str,
    trivy: Path,
    trivy_sha256: str,
    certificate_identity_regexp: str,
) -> None:
    validate_image_ledger(path)
    if not certificate_identity_regexp or "\n" in certificate_identity_regexp:
        raise ValueError("Cosign certificate identity regexp is required")
    for binary, expected in ((cosign, cosign_sha256), (trivy, trivy_sha256)):
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("qualified tool digest is invalid")
        if hashlib.sha256(binary.read_bytes()).hexdigest() != expected:
            raise ValueError(f"qualified tool digest mismatch: {binary.name}")
    if not re.search(r"GitVersion:\s+v3\.1\.4(?:-cogniflow\.1)?\b", _run(cosign, "version")):
        raise ValueError("cosign v3.1.4 is required")
    if "Version: 0.76.2" not in _run(trivy, "--version"):
        raise ValueError("Trivy 0.76.2 is required")

    ledger = json.loads(path.read_text())
    identity = (
        "--certificate-identity-regexp", certificate_identity_regexp,
        "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com",
    )
    for name, item in ledger.items():
        reference = item["reference"]
        _run(cosign, "verify", *identity, reference)
        for attestation_type, predicate, digest_field in (
            ("spdxjson", "spdx", "sbom_sha256"),
            ("slsaprovenance", "slsa", "provenance_sha256"),
        ):
            output = _run(
                cosign, "verify-attestation", "--type", attestation_type, *identity, reference
            )
            payload = _attestation_payload(output, reference, predicate)
            if hashlib.sha256(payload).hexdigest() != item[digest_field]:
                raise ValueError(f"{name} {predicate} evidence digest mismatch")
        report = json.loads(_run(
            trivy, "image", "--format", "json", "--scanners", "vuln",
            "--severity", "HIGH,CRITICAL", "--ignorefile", "/dev/null", reference,
        ))
        if report.get("ArtifactName") != reference or not isinstance(report.get("Results"), list):
            raise ValueError(f"scanner report identity mismatch for {name}")
        findings = [
            finding
            for result in report["Results"]
            if isinstance(result, dict)
            for finding in result.get("Vulnerabilities") or []
            if isinstance(finding, dict)
            and str(finding.get("Severity", "")).upper() in {"HIGH", "CRITICAL"}
        ]
        if findings:
            raise ValueError(f"{name} has HIGH/CRITICAL vulnerabilities")


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
        "qualified_kubectl", "qualified_cosign", "qualified_cosign_sha256",
        "qualified_trivy", "qualified_trivy_sha256",
        "cosign_certificate_identity_regexp", "image_ledger", "controller_matrix", "storage_qualified",
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
        "images": bool(
            plan["image_ledger"] and plan["qualified_cosign"]
            and plan["qualified_cosign_sha256"] and plan["qualified_trivy"]
            and plan["qualified_trivy_sha256"]
        ),
        "kubeconfig": Path(str(plan["kubeconfig"])).is_file(),
        "kubectl": Path(str(plan["qualified_kubectl"])).is_file(),
    }
    if gates["images"]:
        qualify_image_ledger(
            Path(str(plan["image_ledger"])), Path(str(plan["qualified_cosign"])),
            str(plan["qualified_cosign_sha256"]), Path(str(plan["qualified_trivy"])),
            str(plan["qualified_trivy_sha256"]),
            str(plan["cosign_certificate_identity_regexp"]),
        )
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
