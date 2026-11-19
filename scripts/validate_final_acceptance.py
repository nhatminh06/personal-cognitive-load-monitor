"""Independent entry point for CogniFlow final acceptance report validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.final_acceptance import validate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        report = validate(args.report.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({"status": "PASS", "commit_sha": report["commit_sha"]}, sort_keys=True))


if __name__ == "__main__":
    main()
