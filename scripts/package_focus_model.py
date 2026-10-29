"""Package one trusted PR 5 synthetic skops candidate for isolated local tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cogniflow_focus import package_focus_fixture


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--modality", choices=("A", "B", "C"), required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    args = parser.parse_args()
    manifest = package_focus_fixture(
        args.model, args.report, args.dataset_manifest, args.output_dir,
        modality=args.modality, model_name=args.model_name,
        model_version=args.model_version,
    )
    print(json.dumps(manifest.model_dump(mode="json"), sort_keys=True))


if __name__ == "__main__":
    main()
