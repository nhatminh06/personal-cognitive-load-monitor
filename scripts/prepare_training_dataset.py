from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from cogniflow_data.training import prepare_training_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("features", "feature-manifest", "labels", "output", "output-manifest"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--training-cutoff", type=datetime.fromisoformat, required=True)
    parser.add_argument("--git-revision", required=True)
    args = parser.parse_args()
    prepare_training_dataset(
        args.features, args.feature_manifest, args.labels, args.output, args.output_manifest,
        training_cutoff=args.training_cutoff, git_revision=args.git_revision,
    )


if __name__ == "__main__":
    main()
