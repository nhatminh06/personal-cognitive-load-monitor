"""Run local candidate-only behavioral/CV/multimodal experiments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cogniflow_data.multimodal import run_experiments


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("dataset", "manifest", "splits", "output-dir", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--experiment-name", default="cogniflow-multimodal-effort-local")
    parser.add_argument(
        "--validation-scope", choices=("engineering_validation", "empirical_evaluation"),
        required=True,
    )
    parser.add_argument("--register-candidates", action="store_true")
    args = parser.parse_args()
    result = run_experiments(
        args.dataset, args.manifest, args.splits, args.output_dir, args.report,
        tracking_uri=args.tracking_uri, experiment_name=args.experiment_name,
        validation_scope=args.validation_scope, register_candidates=args.register_candidates,
    )
    print(json.dumps({"status": result["status"], "models_registered": result["models_registered"]}))


if __name__ == "__main__":
    main()
