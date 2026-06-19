"""Download a model artifact from MLflow for Docker/KServe packaging.

Usage examples:
    python scripts/download_model_from_mlflow.py \
        --model-uri models:/cognitive-load-classifier/Production \
        --output models/cognitive_load_model.joblib

For local classroom demos, --allow-missing keeps Docker builds working before a
remote MLflow tracking server is available. In production CI, remove
--allow-missing or set REQUIRE_MODEL=true.
"""

from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-uri", default=os.getenv("MODEL_URI", ""))
    parser.add_argument("--output", default=os.getenv("MODEL_PATH", "models/cognitive_load_model.joblib"))
    parser.add_argument("--allow-missing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if not args.model_uri:
        if output.exists():
            print(f"MODEL_URI not set; using existing local model at {output}")
            return
        message = "MODEL_URI is not set and no local model artifact exists."
        if args.allow_missing or os.getenv("REQUIRE_MODEL", "false").lower() != "true":
            print(f"WARNING: {message} Continuing for local/demo build.")
            return
        raise RuntimeError(message)

    try:
        import mlflow

        print(f"Downloading MLflow artifact from {args.model_uri}")
        artifact_dir = Path(mlflow.artifacts.download_artifacts(artifact_uri=args.model_uri))
        if artifact_dir.is_file():
            shutil.copy2(artifact_dir, output)
        else:
            candidates = list(artifact_dir.rglob("*.joblib")) + list(artifact_dir.rglob("*.pkl"))
            if not candidates:
                raise FileNotFoundError(f"No .joblib or .pkl model found under {artifact_dir}")
            shutil.copy2(candidates[0], output)
        print(f"Saved model artifact to {output}")
    except Exception as exc:
        if args.allow_missing or os.getenv("REQUIRE_MODEL", "false").lower() != "true":
            print(f"WARNING: Could not download MLflow model: {exc}. Continuing for local/demo build.")
            return
        raise


if __name__ == "__main__":
    main()
