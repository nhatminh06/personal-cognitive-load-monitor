"""Generate a deterministic synthetic focus-session snapshot for engineering tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cogniflow_data.multimodal import synthetic_snapshot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=90)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(synthetic_snapshot(samples=args.samples, seed=args.seed), indent=2, sort_keys=True)
        + "\n"
    )


if __name__ == "__main__":
    main()
