"""Fail-closed offline qualification and runtime-snapshot checks for Module I."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_CRDS = {
    "inferenceservices.serving.kserve.io",
    "configurations.serving.knative.dev",
    "revisions.serving.knative.dev",
}
REQUIRED_CONTROLLERS = {
    "kserve/kserve-controller-manager",
    "knative-serving/controller",
    "knative-serving/autoscaler",
    "knative-serving/activator",
    "knative-serving/webhook",
    "cert-manager/cert-manager",
}
DIGEST_IMAGE = re.compile(r"[^\s]+@sha256:[a-f0-9]{64}")


def validate_matrix(matrix: dict[str, Any], *, require_qualified: bool = False) -> None:
    candidates = matrix.get("candidates")
    if matrix.get("qualification_status") not in {"BLOCKED", "QUALIFIED"} or not isinstance(candidates, list):
        raise ValueError("compatibility matrix status or candidates are invalid")
    ids = [candidate.get("id") for candidate in candidates]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("compatibility candidate IDs must be unique")
    required = {
        "id", "kserve", "knative_serving", "kubernetes", "networking", "cert_manager",
        "support_status", "integration_evidence", "security_findings", "suitable", "evidence",
    }
    for candidate in candidates:
        if set(candidate) != required or not candidate["evidence"] or any(
            not str(url).startswith("https://") for url in candidate["evidence"]
        ):
            raise ValueError(f"compatibility candidate is incomplete: {candidate.get('id', 'unknown')}")
    selected = matrix.get("selected_candidate")
    selected_rows = [candidate for candidate in candidates if candidate["id"] == selected]
    qualified = (
        matrix["qualification_status"] == "QUALIFIED"
        and len(selected_rows) == 1
        and selected_rows[0]["suitable"] is True
        and selected_rows[0]["support_status"] == "qualified"
    )
    if matrix["qualification_status"] == "QUALIFIED" and not qualified:
        raise ValueError("QUALIFIED requires one suitable selected candidate")
    if require_qualified and not qualified:
        raise ValueError("Module I compatibility is BLOCKED pending exact integration qualification")


def validate_runtime_snapshot(snapshot: dict[str, Any], candidate: dict[str, Any]) -> None:
    expected = {
        "kserve": candidate["kserve"],
        "knative_serving": candidate["knative_serving"],
        "kubernetes": candidate["kubernetes"],
        "networking": candidate["networking"],
        "cert_manager": candidate["cert_manager"],
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise ValueError("runtime versions do not match the qualified matrix")
    if set(snapshot.get("crds", [])) != REQUIRED_CRDS:
        raise ValueError("required KServe/Knative CRD inventory does not match")
    controllers = snapshot.get("controllers", {})
    if set(controllers) != REQUIRED_CONTROLLERS or any(
        value.get("available") is not True or not DIGEST_IMAGE.fullmatch(str(value.get("image", "")))
        for value in controllers.values()
    ):
        raise ValueError("controller inventory must be complete, available and digest-pinned")
    autoscaler = snapshot.get("autoscaler", {})
    if autoscaler != {
        "enable-scale-to-zero": "true", "stable-window": "60s", "scale-to-zero-grace-period": "30s"
    }:
        raise ValueError("global Knative scale-to-zero settings do not match")
    revision = snapshot.get("revision_annotations", {})
    if revision != {
        "autoscaling.knative.dev/class": "kpa.autoscaling.knative.dev",
        "autoscaling.knative.dev/min-scale": "0",
        "autoscaling.knative.dev/max-scale": "3",
        "autoscaling.knative.dev/target": "1",
    }:
        raise ValueError("effective Revision autoscaling annotations do not match")
    routes = snapshot.get("routes", {})
    model = snapshot.get("model_name")
    namespace = snapshot.get("namespace")
    origin = f"http://{model}-predictor.{namespace}.svc.cluster.local"
    if routes != {
        "origin": origin,
        "predict": f"{origin}/v1/models/{model}:predict",
        "metadata": f"{origin}/v1/models/{model}/metadata",
    }:
        raise ValueError("KServe predictor routes do not match the internal service contract")
    timeouts = snapshot.get("timeouts", {})
    if timeouts != {
        "api_seconds": 30, "ingress_seconds": 35, "revision_seconds": 35,
        "response_start_seconds": 35, "idle_seconds": 35,
    }:
        raise ValueError("cold-start timeout chain must be finite and ordered")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--require-qualified", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text())
    validate_matrix(matrix, require_qualified=args.require_qualified)
    if args.snapshot:
        selected = next(row for row in matrix["candidates"] if row["id"] == matrix["selected_candidate"])
        validate_runtime_snapshot(json.loads(args.snapshot.read_text()), selected)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, StopIteration, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
