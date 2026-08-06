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
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from preprocessing_api.features import FEATURE_COLUMNS  # noqa: E402


def manifest_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".manifest.json")


def _write_manifest(output: Path, model_uri: str | None, source: str) -> None:
    """Record where the packaged model artifact actually came from.

    Read by GET /model-info so the running API can report its own model
    provenance instead of the operator having to trust that a build step ran
    correctly. Deliberately excludes MLFLOW_TRACKING_URI's value (may point at
    an internal-only host) — only whether one was configured.
    """

    manifest = {
        "model_uri": model_uri,
        "source": source,
        "feature_columns": FEATURE_COLUMNS,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "mlflow_tracking_configured": bool(os.getenv("MLFLOW_TRACKING_URI")),
    }
    manifest_path(output).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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
            if not manifest_path(output).exists():
                _write_manifest(output, model_uri=None, source="local-existing")
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
        _write_manifest(output, model_uri=args.model_uri, source="mlflow")
        print(f"Saved model artifact to {output}")
    except Exception as exc:
        if args.allow_missing or os.getenv("REQUIRE_MODEL", "false").lower() != "true":
            print(f"WARNING: Could not download MLflow model: {exc}. Continuing for local/demo build.")
            return
        raise


if __name__ == "__main__":
    main()
