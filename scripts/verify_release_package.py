"""Fail-closed verification for the model package crossing GitHub job boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


EXPECTED_FILES = {"cognitive_load_model.skops", "model-package.json"}
EXPECTED_KEYS = {
    "contract_version", "approval_status", "approval_scope", "approval_repository",
    "approval_workflow", "approval_workflow_run_id", "approval_git_commit",
    "approval_environment", "model_name", "model_version", "run_id",
    "registered_artifact_sha256", "packaged_model_sha256", "dataset_sha256",
    "feature_schema_version", "feature_names", "label_provenance", "git_revision",
    "approved_by", "approved_at",
}


def package_sha256(package: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(package.iterdir()):
        relative = item.name.encode()
        payload = item.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def verify_package(
    package: Path,
    *,
    model_name: str,
    model_version: str,
    run_id: str,
    git_revision: str,
    artifact_sha256: str,
    workflow_run_id: str,
    expected_package_sha256: str | None = None,
) -> str:
    if not package.is_dir() or {item.name for item in package.iterdir()} != EXPECTED_FILES:
        raise ValueError("release package must contain exactly the model and manifest")
    if any(item.is_symlink() or not item.is_file() for item in package.iterdir()):
        raise ValueError("release package entries must be regular files")

    manifest = json.loads((package / "model-package.json").read_text())
    if not isinstance(manifest, dict) or set(manifest) != EXPECTED_KEYS:
        raise ValueError("release package manifest has unexpected fields")
    expected = {
        "contract_version": "1.0",
        "approval_status": "approved",
        "approval_scope": "solo_owner_educational_decision",
        "approval_repository": "nhatminh06/personal-cognitive-load-monitor",
        "approval_workflow": (
            "nhatminh06/personal-cognitive-load-monitor/"
            ".github/workflows/release.yaml@refs/heads/main"
        ),
        "approval_workflow_run_id": workflow_run_id,
        "approval_git_commit": git_revision,
        "approval_environment": "production-release",
        "model_name": model_name,
        "model_version": model_version,
        "run_id": run_id,
        "registered_artifact_sha256": artifact_sha256,
        "feature_schema_version": "1.0",
        "label_provenance": "synthetic_proxy",
        "git_revision": git_revision,
        "approved_by": "github-owner:nhatminh06",
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("release package identity or provenance mismatch")
    for key in ("packaged_model_sha256", "dataset_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get(key, ""))):
            raise ValueError(f"invalid {key}")
    model_digest = hashlib.sha256(
        (package / "cognitive_load_model.skops").read_bytes()
    ).hexdigest()
    if model_digest != manifest["packaged_model_sha256"]:
        raise ValueError("packaged model digest mismatch")

    digest = package_sha256(package)
    if expected_package_sha256 is not None and digest != expected_package_sha256:
        raise ValueError("transferred package digest mismatch")
    return digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-revision", required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--expected-package-sha256")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    digest = verify_package(
        args.package,
        model_name=args.model_name,
        model_version=args.model_version,
        run_id=args.run_id,
        git_revision=args.git_revision,
        artifact_sha256=args.artifact_sha256,
        workflow_run_id=args.workflow_run_id,
        expected_package_sha256=args.expected_package_sha256,
    )
    if args.github_output:
        with args.github_output.open("a") as output:
            output.write(f"package_sha256={digest}\n")
    print(digest)


if __name__ == "__main__":
    main()
