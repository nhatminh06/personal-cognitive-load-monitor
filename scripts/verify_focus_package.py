"""Verify a local focus-model package without running inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cogniflow_focus import validate_focus_package
from cogniflow_focus.package import enforce_local_fixture_governance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    manifest, _ = validate_focus_package(args.package)
    enforce_local_fixture_governance(manifest)
    print(json.dumps({
        "model_name": manifest.model_name,
        "package_sha256": manifest.package_sha256,
        "provenance_classification": manifest.provenance_classification,
        "approval_status": manifest.approval_status,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
