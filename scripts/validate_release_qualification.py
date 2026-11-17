"""Fail-closed validation for an offline M10 release-qualification bundle."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
IMAGE = re.compile(
    r"[a-z0-9-]+-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/"
    r"cogniflow-images/[a-z0-9-]+@sha256:[0-9a-f]{64}"
)
EXPECTED_IMAGES = {
    "anomaly-detector", "cognitive-load-api", "cogniflow-kserve", "event-consumer"
}


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _scan_passed(path: Path, image: str) -> None:
    report = _object(path)
    if report.get("ArtifactName") != image or not isinstance(report.get("Results"), list):
        raise ValueError(f"scanner report identity mismatch for {image}")
    vulnerabilities = [
        finding
        for result in report["Results"]
        if isinstance(result, dict)
        for finding in result.get("Vulnerabilities") or []
        if isinstance(finding, dict)
        and str(finding.get("Severity", "")).upper() in {"HIGH", "CRITICAL"}
    ]
    if vulnerabilities:
        raise ValueError(f"{image} has HIGH/CRITICAL vulnerabilities")


def validate(bundle_path: Path, scan_dir: Path, expected_commit: str) -> None:
    if not COMMIT.fullmatch(expected_commit):
        raise ValueError("expected commit must be a full lowercase Git SHA")
    bundle = _object(bundle_path)
    if set(bundle) != {"source_commit", "authorization", "model", "images"}:
        raise ValueError("qualification bundle has unexpected fields")
    authorization = bundle["authorization"]
    if authorization != {
        "approved": True,
        "environment": "m10-release-qualification",
        "actor": "github-owner:nhatminh06",
    }:
        raise ValueError("exact owner authorization is required")
    if bundle["source_commit"] != expected_commit:
        raise ValueError("qualification bundle is not bound to the expected commit")

    model = bundle["model"]
    if not isinstance(model, dict) or set(model) != {
        "approval_status", "approval_commit", "artifact_sha256", "dataset_sha256",
        "package_sha256",
    }:
        raise ValueError("invalid model identity")
    if model["approval_status"] != "approved" or model["approval_commit"] != expected_commit:
        raise ValueError("a candidate model cannot be released")
    if any(not SHA256.fullmatch(str(model[key])) for key in (
        "artifact_sha256", "dataset_sha256", "package_sha256"
    )):
        raise ValueError("invalid model provenance digest")

    images = bundle["images"]
    if not isinstance(images, dict) or set(images) != EXPECTED_IMAGES:
        raise ValueError("qualification requires exactly the four release images")
    seen: set[str] = set()
    for name, identity in images.items():
        if not isinstance(identity, dict) or set(identity) != {
            "reference", "source_commit", "model_package_sha256", "sbom_sha256",
            "provenance_sha256",
        }:
            raise ValueError(f"invalid image identity for {name}")
        reference = identity["reference"]
        if not isinstance(reference, str) or not IMAGE.fullmatch(reference):
            raise ValueError(f"invalid immutable image reference for {name}")
        if not reference.split("@", 1)[0].endswith(f"/{name}") or reference in seen:
            raise ValueError(f"image name or identity mismatch for {name}")
        if identity["source_commit"] != expected_commit:
            raise ValueError(f"image source commit mismatch for {name}")
        if identity["model_package_sha256"] != model["package_sha256"]:
            raise ValueError(f"model and image identity mismatch for {name}")
        if any(not SHA256.fullmatch(str(identity[key])) for key in (
            "sbom_sha256", "provenance_sha256"
        )):
            raise ValueError(f"invalid supply-chain digest for {name}")
        scan = scan_dir / f"{name}.trivy.json"
        if not scan.is_file():
            raise ValueError(f"missing scanner report for {name}")
        _scan_passed(scan, reference)
        seen.add(reference)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--scan-dir", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    validate(args.bundle, args.scan_dir, args.expected_commit)


if __name__ == "__main__":
    main()
