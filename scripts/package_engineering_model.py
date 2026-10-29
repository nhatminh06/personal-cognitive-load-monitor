"""Package a verified Module I 2B candidate for synthetic local serving only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cogniflow_kserve.engineering import package_engineering_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = package_engineering_model(
        args.source_model,
        args.report,
        args.validation,
        args.output_dir,
        expected_source_sha256=args.expected_source_sha256,
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
