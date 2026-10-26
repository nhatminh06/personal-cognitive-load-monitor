"""Compile the digest-pinned CogniFlow KFP v2 pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from kfp import compiler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipelines.cogniflow_training_pipeline import build_pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--component-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(
        pipeline_func=build_pipeline(args.component_image),
        package_path=str(args.output),
    )


if __name__ == "__main__":
    main()
