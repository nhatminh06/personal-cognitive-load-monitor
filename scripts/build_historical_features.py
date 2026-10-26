"""Build a bounded historical-feature artifact from deterministic JSON fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cogniflow_data.historical import (
    FeatureDecision,
    SilverFeatureEvent,
    SourceSnapshot,
    select_historical_features,
    write_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()
    fixture = json.loads(args.input.read_text())
    rows = select_historical_features(
        [SilverFeatureEvent.model_validate(item) for item in fixture["events"]],
        [FeatureDecision.model_validate(item) for item in fixture["decisions"]],
        SourceSnapshot.model_validate(fixture["snapshot"]),
    )
    print(json.dumps(write_dataset(rows, args.output, args.metadata, code_revision=args.code_revision)))


if __name__ == "__main__":
    main()
