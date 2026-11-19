"""Generate and independently validate CogniFlow final acceptance evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable


CHECKS = (
    "api_authentication_readiness",
    "kserve_inference_recovery",
    "kfp_run_provenance",
    "mlflow_candidate_registration",
    "gcs_artifact_integrity",
    "knative_delivery",
    "anomaly_persistence_recovery",
    "kafka_bronze_ingestion",
    "spark_delta_processing",
    "trino_dbt_reconciliation",
    "cloud_deployment_readiness",
)
STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(
    r"[a-z0-9-]+-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/"
    r"cogniflow-images/[a-z0-9-]+@sha256:[0-9a-f]{64}"
)
RUNTIME_PREREQUISITES = {
    "owner_authorization",
    "approved_gcp_project",
    "terraform_plan_reviewed",
    "budget_approved",
    "controller_versions_supported",
    "remote_images_qualified",
    "cosign_signatures_verified",
    "spdx_attestations_verified",
    "slsa_attestations_verified",
    "zero_high_critical_scans",
    "model_approved",
    "network_policy_reviewed",
}
LOCAL_TESTS = (
    "src/tests/test_api.py",
    "src/tests/test_model_client.py",
    "src/tests/test_kserve_predictor.py",
    "src/tests/test_kfp_pipeline.py",
    "src/tests/test_kfp_tasks.py",
    "src/tests/test_gcs_artifacts.py",
    "src/tests/test_activity_events.py",
    "src/tests/test_anomaly_detection.py",
    "src/tests/test_bronze.py",
    "src/tests/test_module2_bulk.py",
)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _commit(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    )
    revision = result.stdout.strip()
    if not COMMIT.fullmatch(revision):
        raise ValueError("Git did not return a full commit SHA")
    return revision


def _blocked_checks() -> dict[str, dict[str, Any]]:
    reasons = {
        "api_authentication_readiness": "authorized API and KServe runtime unavailable",
        "kserve_inference_recovery": "no approved model deployment or mutation authorization",
        "kfp_run_provenance": "no authorized KFP runtime run",
        "mlflow_candidate_registration": "no KFP-produced cloud registry identity",
        "gcs_artifact_integrity": "real GCS access not authorized; local storage is mocked",
        "knative_delivery": "durable authenticated Eventing runtime unavailable",
        "anomaly_persistence_recovery": "no authorized Knative failure/recovery run",
        "kafka_bronze_ingestion": "no authorized integrated runtime ingestion",
        "spark_delta_processing": "Spark image remains blocked by SEC-022 qualification",
        "trino_dbt_reconciliation": "no runtime Silver/Gold stage evidence",
        "cloud_deployment_readiness": "GCP provisioning and Kubernetes mutation not authorized",
    }
    return {
        name: {"status": "BLOCKED", "scope": "runtime", "reason": reasons[name], "evidence": []}
        for name in CHECKS
    }


def run_offline(
    root: Path,
    output_dir: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    additional_evidence: tuple[Path, ...] = (),
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    log = output_dir / "offline-contract-tests.txt"
    command = [str(root / ".venv/bin/pytest"), "-q", *LOCAL_TESTS]
    result = runner(command, cwd=root, capture_output=True, text=True)
    log.write_text(result.stdout + result.stderr)
    log.chmod(0o600)
    status = "PASS" if result.returncode == 0 else "FAIL"
    evidence = [{"path": log.name, "sha256": _digest(log)}]
    for artifact in additional_evidence:
        if artifact.parent.resolve() != output_dir.resolve() or not artifact.is_file():
            raise ValueError("additional evidence must be a file inside the output directory")
        evidence.append({"path": artifact.name, "sha256": _digest(artifact)})
    report = {
        "schema_version": "1.0",
        "commit_sha": _commit(root),
        "environment": {"kind": "local_offline", "identity": "developer-workstation"},
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "authorization": {"cloud_operations_authorized": False},
        "prerequisites": {name: False for name in sorted(RUNTIME_PREREQUISITES)},
        "identities": {
            "images": {}, "dataset": None, "model": None, "kfp_run_id": None,
            "mlflow": None, "gcs": None, "kubernetes_resources": {},
        },
        "local_validation": {
            "status": status,
            "scope": "local_contract",
            "command": command,
            "evidence": evidence,
        },
        "checks": _blocked_checks(),
        "uncompleted_criteria": list(CHECKS),
    }
    report_path = output_dir / "acceptance-report.json"
    if report_path.exists():
        raise FileExistsError(f"acceptance report already exists: {report_path}")
    _write_new(report_path, report)
    return report_path


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("acceptance report must be a JSON object")
    return value


def _verify_evidence(root: Path, evidence: Any) -> None:
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("PASS requires at least one evidence artifact")
    for reference in evidence:
        if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
            raise ValueError("invalid evidence reference")
        relative = Path(str(reference["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("evidence paths must remain inside the report directory")
        artifact = root / relative
        if not artifact.is_file() or artifact.is_symlink() or artifact.stat().st_size > 5 * 1024 * 1024:
            raise ValueError("evidence artifact is missing, unsafe or oversized")
        if not SHA256.fullmatch(str(reference["sha256"])) or _digest(artifact) != reference["sha256"]:
            raise ValueError("evidence digest mismatch")


def _validate_runtime_identities(report: dict[str, Any]) -> None:
    identities = report.get("identities")
    if not isinstance(identities, dict):
        raise ValueError("runtime identities are missing")
    images = identities.get("images")
    if not isinstance(images, dict) or not images or any(
        not isinstance(value, str) or not IMAGE.fullmatch(value) for value in images.values()
    ):
        raise ValueError("runtime PASS requires remote image digests")
    model = identities.get("model")
    if not isinstance(model, dict) or model.get("approval_status") != "approved" or any(
        not SHA256.fullmatch(str(model.get(key, "")))
        for key in ("artifact_sha256", "package_sha256", "dataset_sha256")
    ):
        raise ValueError("runtime PASS requires an exact approved model identity")


def _validate_check_identity(name: str, identities: dict[str, Any]) -> None:
    if name == "kfp_run_provenance" and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]{7,127}", str(identities.get("kfp_run_id", ""))
    ):
        raise ValueError("KFP runtime PASS requires an exact run ID")
    if name == "mlflow_candidate_registration":
        mlflow = identities.get("mlflow")
        if not isinstance(mlflow, dict) or not re.fullmatch(
            r"[0-9a-f]{32}", str(mlflow.get("run_id", ""))
        ) or not re.fullmatch(r"[1-9][0-9]*", str(mlflow.get("model_version", ""))):
            raise ValueError("MLflow runtime PASS requires exact run and model-version identities")
    if name == "gcs_artifact_integrity":
        gcs = identities.get("gcs")
        if (
            not isinstance(gcs, dict)
            or not isinstance(gcs.get("generation"), int)
            or gcs["generation"] < 1
            or not SHA256.fullmatch(str(gcs.get("sha256", "")))
            or not str(gcs.get("uri", "")).startswith("gs://")
        ):
            raise ValueError("GCS runtime PASS requires URI, generation and SHA-256")
    if name in {
        "api_authentication_readiness", "kserve_inference_recovery", "knative_delivery",
        "anomaly_persistence_recovery", "cloud_deployment_readiness",
    } and not identities.get("kubernetes_resources"):
        raise ValueError("Kubernetes runtime PASS requires exact resource identities")
    if name in {
        "kafka_bronze_ingestion", "spark_delta_processing", "trino_dbt_reconciliation",
    } and not SHA256.fullmatch(str((identities.get("dataset") or {}).get("sha256", ""))):
        raise ValueError("data runtime PASS requires an exact dataset SHA-256")


def validate(report_path: Path) -> dict[str, Any]:
    report = _load(report_path)
    required = {
        "schema_version", "commit_sha", "environment", "executed_at", "authorization",
        "prerequisites", "identities", "local_validation", "checks", "uncompleted_criteria",
    }
    if set(report) != required or report["schema_version"] != "1.0":
        raise ValueError("acceptance report schema is unsupported")
    if not COMMIT.fullmatch(str(report["commit_sha"])):
        raise ValueError("acceptance report commit is invalid")
    datetime.fromisoformat(str(report["executed_at"]).replace("Z", "+00:00"))
    checks = report["checks"]
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        raise ValueError("acceptance report checks are incomplete")
    environment = report["environment"]
    authorization = report["authorization"]
    prerequisites = report["prerequisites"]
    runtime_pass = any(item.get("status") == "PASS" for item in checks.values())
    if runtime_pass:
        if environment.get("kind") != "gke_runtime" or authorization != {
            "cloud_operations_authorized": True
        }:
            raise ValueError("local or unauthorized evidence cannot claim runtime PASS")
        if set(prerequisites) != RUNTIME_PREREQUISITES or not all(prerequisites.values()):
            raise ValueError("runtime PASS requires every security prerequisite")
        _validate_runtime_identities(report)
    for name, check in checks.items():
        if not isinstance(check, dict) or check.get("status") not in STATUSES:
            raise ValueError(f"invalid acceptance status for {name}")
        if check["status"] == "PASS":
            if check.get("scope") != "runtime":
                raise ValueError("acceptance PASS must represent runtime evidence")
            _verify_evidence(report_path.parent, check.get("evidence"))
            _validate_check_identity(name, report["identities"])
    incomplete = [name for name in CHECKS if checks[name]["status"] != "PASS"]
    if report["uncompleted_criteria"] != incomplete:
        raise ValueError("uncompleted criteria do not match acceptance decisions")
    local = report["local_validation"]
    if local.get("status") == "PASS":
        _verify_evidence(report_path.parent, local.get("evidence"))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    offline = subparsers.add_parser("offline")
    offline.add_argument("--root", type=Path, default=Path.cwd())
    offline.add_argument("--output-dir", type=Path, required=True)
    offline.add_argument("--additional-evidence", action="append", type=Path, default=[])
    verify = subparsers.add_parser("validate")
    verify.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "offline":
            path = run_offline(
                args.root.resolve(), args.output_dir.resolve(),
                additional_evidence=tuple(item.resolve() for item in args.additional_evidence),
            )
            report = validate(path)
            print(path)
            if report["local_validation"]["status"] != "PASS":
                raise SystemExit("offline acceptance contracts failed")
        else:
            report = validate(args.report.resolve())
            print(json.dumps({"status": "PASS", "commit_sha": report["commit_sha"]}, sort_keys=True))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
