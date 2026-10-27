"""Validate and render non-secret Module I acceptance evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

STATUSES = {
    "implemented",
    "statically_verified",
    "locally_runtime_verified",
    "ci_verified",
    "cloud_runtime_verified",
    "blocked",
}
CRITERIA = (
    "ci_cd",
    "metrics",
    "tracing",
    "logging",
    "drift",
    "gateway",
    "fastapi_hpa",
    "kserve_scale_to_zero",
    "kubernetes_iac",
    "model_provenance",
    "rollback_teardown",
)
CLOUD_REQUIRED_STATUS = {criterion: "cloud_runtime_verified" for criterion in CRITERIA}
CLOUD_REQUIRED_STATUS["ci_cd"] = "ci_verified"
IMAGE_RE = re.compile(r"[a-z0-9-]+-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/[a-z0-9-]+/[a-z0-9-]+@sha256:[a-f0-9]{64}")
SHA_RE = re.compile(r"[a-f0-9]{64}")
SECRET_KEY_RE = re.compile(r"(password|token|secret|credential|authorization|api[_-]?key)", re.IGNORECASE)


def _reject_secret_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY_RE.search(key):
                raise ValueError(f"secret-bearing evidence key is forbidden: {path}.{key}")
            _reject_secret_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_keys(child, f"{path}[{index}]")


def validate_evidence(payload: dict[str, Any], expected_context: str, require_cloud: bool) -> None:
    _reject_secret_keys(payload)
    if payload.get("schema_version") != "1.0":
        raise ValueError("unsupported evidence schema_version")
    identity = payload.get("identity", {})
    if identity.get("kubernetes_context") != expected_context:
        raise ValueError("Kubernetes context does not match the separately authorized target")
    if not re.fullmatch(r"[0-9a-f]{40}", str(identity.get("git_commit", ""))):
        raise ValueError("identity.git_commit must be an exact commit SHA")
    if identity.get("namespace") != "cogniflow":
        raise ValueError("identity.namespace must be cogniflow")
    for key in ("cluster_uid", "namespace_uid"):
        if not str(identity.get(key, "")).strip():
            raise ValueError(f"identity.{key} is required")

    release = payload.get("release", {})
    for key in ("api_image", "kserve_image"):
        if not IMAGE_RE.fullmatch(str(release.get(key, ""))):
            raise ValueError(f"release.{key} must be an immutable Artifact Registry digest reference")
    model = release.get("model", {})
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?", str(model.get("name", ""))):
        raise ValueError("release.model.name must match the KServe DNS-label contract")
    if not str(model.get("version", "")).isdigit() or int(model["version"]) < 1:
        raise ValueError("release.model.version must be a positive immutable version")
    for key in ("model_sha256", "artifact_sha256", "dataset_sha256"):
        if not SHA_RE.fullmatch(str(model.get(key, ""))):
            raise ValueError(f"release.model.{key} must be a SHA-256")

    checks = payload.get("checks", {})
    if set(checks) != set(CRITERIA):
        raise ValueError("checks must contain every Module I acceptance criterion exactly once")
    for criterion in CRITERIA:
        check = checks[criterion]
        if check.get("status") not in STATUSES or not str(check.get("evidence", "")).strip():
            raise ValueError(f"checks.{criterion} requires a valid status and evidence reference")
        if require_cloud and check["status"] != CLOUD_REQUIRED_STATUS[criterion]:
            raise ValueError(f"checks.{criterion} has not reached {CLOUD_REQUIRED_STATUS[criterion]}")

    if require_cloud:
        replicas = payload.get("replicas", {})
        if replicas.get("kserve_idle") != 0 or int(replicas.get("kserve_cold_start", 0)) < 1:
            raise ValueError("KServe evidence must show zero idle replicas and a cold-start activation")
        if not (
            int(replicas.get("hpa_initial", 0)) >= 1
            and int(replicas.get("hpa_peak", 0)) > int(replicas["hpa_initial"])
            and int(replicas.get("hpa_final", 0)) == int(replicas["hpa_initial"])
        ):
            raise ValueError("HPA evidence must show bounded scale-up and return to its initial count")


def render_report(payload: dict[str, Any]) -> str:
    identity = payload["identity"]
    release = payload["release"]
    lines = [
        "# Module I acceptance report",
        "",
        f"- Git commit: `{identity['git_commit']}`",
        f"- Kubernetes context: `{identity['kubernetes_context']}`",
        f"- Namespace: `{identity['namespace']}`",
        f"- API image: `{release['api_image']}`",
        f"- KServe image: `{release['kserve_image']}`",
        f"- Model: `{release['model']['name']}/{release['model']['version']}`",
        "",
        "| Criterion | Status | Evidence |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {criterion.replace('_', ' ')} | {payload['checks'][criterion]['status']} | "
        f"{payload['checks'][criterion]['evidence']} |"
        for criterion in CRITERIA
    )
    return "\n".join(lines) + "\n"


def write_report(path: Path, report: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as stream:
            descriptor = -1
            stream.write(report)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--expected-context", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--require-cloud-acceptance", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.evidence.read_text())
    validate_evidence(payload, args.expected_context, args.require_cloud_acceptance)
    write_report(args.report, render_report(payload))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
