"""Validate and render non-secret Module I acceptance evidence."""

from __future__ import annotations

import argparse
import hashlib
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
SECRET_KEY_RE = re.compile(
    r"(password|token|secret|credential|authorization|api[_-]?key|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:Bearer|Basic)\s+\S+", re.IGNORECASE)
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024


def _reject_secret_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SECRET_KEY_RE.search(key):
                raise ValueError(f"secret-bearing evidence key is forbidden: {path}.{key}")
            _reject_secret_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_keys(child, f"{path}[{index}]")
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        raise ValueError(f"credential-like evidence value is forbidden: {path}")


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
        artifact = check.get("evidence", {})
        if (
            check.get("status") not in STATUSES
            or set(artifact) != {"path", "sha256"}
            or not isinstance(artifact.get("path"), str)
            or not SHA_RE.fullmatch(str(artifact.get("sha256", "")))
        ):
            raise ValueError(f"checks.{criterion} requires a valid status and evidence reference")
        if require_cloud and check["status"] != CLOUD_REQUIRED_STATUS[criterion]:
            raise ValueError(f"checks.{criterion} has not reached {CLOUD_REQUIRED_STATUS[criterion]}")

    if require_cloud:
        replicas = payload.get("replicas", {})
        cold_start_seconds = float(replicas.get("kserve_cold_start_seconds", 0))
        if (
            replicas.get("kserve_idle") != 0
            or int(replicas.get("kserve_cold_start", 0)) < 1
            or not 0 < cold_start_seconds <= 30
            or replicas.get("kserve_prediction_succeeded") is not True
        ):
            raise ValueError(
                "KServe evidence must show zero idle replicas, bounded activation and a successful prediction"
            )
        if not (
            int(replicas.get("hpa_initial", 0)) >= 1
            and int(replicas.get("hpa_peak", 0)) > int(replicas["hpa_initial"])
            and int(replicas.get("hpa_final", 0)) == int(replicas["hpa_initial"])
        ):
            raise ValueError("HPA evidence must show bounded scale-up and return to its initial count")


def verify_artifacts(payload: dict[str, Any], artifact_root: Path) -> dict[str, str]:
    root = artifact_root.resolve(strict=True)
    if not root.is_dir() or artifact_root.is_symlink():
        raise ValueError("artifact root must be a real directory")
    verified: dict[str, str] = {}
    seen: set[str] = set()
    for criterion in CRITERIA:
        reference = payload["checks"][criterion]["evidence"]
        relative = reference["path"]
        path_parts = Path(relative)
        if (
            path_parts.is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in path_parts.parts)
            or path_parts.suffix != ".json"
        ):
            raise ValueError(f"unsafe evidence path for {criterion}")
        normalized = path_parts.as_posix()
        if normalized in seen:
            raise ValueError(f"duplicate evidence path: {normalized}")
        seen.add(normalized)
        candidate = root.joinpath(path_parts)
        parents = [root.joinpath(*path_parts.parts[:index]) for index in range(1, len(path_parts.parts))]
        if (
            candidate.is_symlink()
            or any(parent.is_symlink() for parent in parents)
            or not candidate.is_file()
            or not candidate.resolve(strict=True).is_relative_to(root)
        ):
            raise ValueError(f"evidence artifact is missing or unsafe: {normalized}")
        if candidate.stat().st_size > MAX_ARTIFACT_BYTES:
            raise ValueError(f"evidence artifact exceeds 5 MiB: {normalized}")
        content = candidate.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != reference["sha256"]:
            raise ValueError(f"evidence artifact SHA-256 changed: {normalized}")
        try:
            artifact_payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"evidence artifact must be sanitized JSON: {normalized}") from error
        _reject_secret_keys(artifact_payload, f"artifact:{normalized}")
        verified[criterion] = actual
    return verified


def render_report(payload: dict[str, Any], verified: dict[str, str] | None = None) -> str:
    identity = payload["identity"]
    release = payload["release"]
    lines = [
        "# Module I evidence integrity report",
        "",
        "- Outcome: **INDEPENDENT RUNTIME REVIEW REQUIRED**",
        f"- Artifact integrity: {'verified' if verified is not None else 'not verified (schema only)'}",
        "- This report does not independently prove that Kubernetes events occurred.",
        f"- Git commit: `{identity['git_commit']}`",
        f"- Kubernetes context: `{identity['kubernetes_context']}`",
        f"- Cluster UID: `{identity['cluster_uid']}`",
        f"- Namespace: `{identity['namespace']}`",
        f"- Namespace UID: `{identity['namespace_uid']}`",
        f"- API image: `{release['api_image']}`",
        f"- KServe image: `{release['kserve_image']}`",
        f"- Model: `{release['model']['name']}/{release['model']['version']}`",
        f"- Model SHA-256: `{release['model']['model_sha256']}`",
        f"- Registered artifact SHA-256: `{release['model']['artifact_sha256']}`",
        f"- Dataset SHA-256: `{release['model']['dataset_sha256']}`",
        "",
        "| Criterion | Status | Evidence |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {criterion.replace('_', ' ')} | {payload['checks'][criterion]['status']} | "
        f"`{payload['checks'][criterion]['evidence']['path']}` / "
        f"`{payload['checks'][criterion]['evidence']['sha256']}` |"
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
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--require-cloud-acceptance", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.evidence.read_text())
    validate_evidence(payload, args.expected_context, args.require_cloud_acceptance)
    if args.require_cloud_acceptance and args.artifact_root is None:
        raise ValueError("--artifact-root is required for a cloud evidence bundle")
    verified = verify_artifacts(payload, args.artifact_root) if args.artifact_root else None
    write_report(args.report, render_report(payload, verified))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
