"""Create a disposable synthetic .skops package without touching MLflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import skops.io
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from preprocessing_api.features import FEATURE_NAMES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    features = pd.DataFrame(
        [
            [150, 10, 0, 96, 0.9375, 0.0625],
            [90, 60, 3, 24, 0.6, 0.4],
            [30, 120, 8, 4, 0.2, 0.8],
        ],
        columns=FEATURE_NAMES,
    )
    model = RandomForestClassifier(n_estimators=2, random_state=22).fit(
        features, ["LOW", "MEDIUM", "HIGH"]
    )
    model_path = args.output / "cognitive_load_model.skops"
    skops.io.dump(model, model_path)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    synthetic_digest = hashlib.sha256(b"cogniflow-module1-qualification").hexdigest()
    manifest = {
        "contract_version": "1.0", "approval_status": "approved",
        "model_name": "qualification-model", "model_version": "1",
        "registered_artifact_sha256": synthetic_digest, "packaged_model_sha256": digest,
        "dataset_sha256": synthetic_digest, "feature_schema_version": "1.0",
        "feature_names": list(FEATURE_NAMES), "label_provenance": "synthetic_proxy",
        "run_id": "disposable-qualification", "registered_source": "local://disposable-qualification",
        "git_revision": "0" * 40, "approved_by": "disposable-qualification-only",
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    (args.output / "model-package.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"model_sha256": digest, "artifact_sha256": synthetic_digest, "dataset_sha256": synthetic_digest}))


if __name__ == "__main__":
    main()
