"""Validated historical training-set preparation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from preprocessing_api.features import FEATURE_NAMES

from .historical import HistoricalFeatureRow, SyntheticLabel


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path, model: type[HistoricalFeatureRow] | type[SyntheticLabel]) -> list[Any]:
    if not path.is_file():
        raise ValueError(f"required input is unavailable: {path}")
    return [model.model_validate_json(line) for line in path.read_text().splitlines() if line]


def prepare_training_dataset(
    feature_path: Path,
    feature_manifest_path: Path,
    label_path: Path,
    output_path: Path,
    output_manifest_path: Path,
    *,
    training_cutoff: datetime,
    git_revision: str,
) -> dict[str, Any]:
    if training_cutoff.tzinfo is None or training_cutoff.utcoffset() is None:
        raise ValueError("training cutoff must include a timezone")
    cutoff = training_cutoff.astimezone(UTC)
    manifest = json.loads(feature_manifest_path.read_text())
    if manifest.get("sha256") != sha256(feature_path):
        raise ValueError("feature manifest checksum mismatch")
    if manifest.get("feature_schema_version") != "1.0" or manifest.get("feature_names") != list(FEATURE_NAMES):
        raise ValueError("unsupported feature manifest contract")

    features = load_jsonl(feature_path, HistoricalFeatureRow)
    labels = load_jsonl(label_path, SyntheticLabel)
    label_by_id: dict[str, SyntheticLabel] = {}
    for label in labels:
        if label.decision_id in label_by_id:
            raise ValueError(f"duplicate label decision_id: {label.decision_id}")
        label_by_id[label.decision_id] = label

    joined: list[dict[str, Any]] = []
    for feature in sorted(features, key=lambda row: (row.decision_time, row.decision_id)):
        if feature.available_at > feature.decision_time:
            raise ValueError("future feature availability detected")
        label = label_by_id.get(feature.decision_id)
        if label is None:
            raise ValueError(f"missing label: {feature.decision_id}")
        if label.available_at > cutoff:
            raise ValueError(f"label unavailable by cutoff: {feature.decision_id}")
        joined.append(
            {
                "decision_id": feature.decision_id,
                "decision_time": feature.decision_time.isoformat(),
                "feature_available_at": feature.available_at.isoformat(),
                "label_available_at": label.available_at.isoformat(),
                **{name: getattr(feature, name) for name in FEATURE_NAMES},
                "label": label.label,
                "label_provenance": label.provenance,
            }
        )
    payload = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in joined).encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    count = len(joined)
    train_end, validation_end = int(count * 0.6), int(count * 0.8)
    result = {
        "contract_version": "1.0",
        "dataset_id": "cogniflow-module3-training-synthetic-v1",
        "dataset_sha256": hashlib.sha256(payload).hexdigest(),
        "feature_input_sha256": sha256(feature_path),
        "label_input_sha256": sha256(label_path),
        "feature_schema_version": "1.0",
        "feature_names": list(FEATURE_NAMES),
        "source_dataset": manifest["source_dataset"],
        "source_delta_versions": manifest.get("source_delta_versions", []),
        "git_revision": git_revision,
        "training_cutoff": cutoff.isoformat(),
        "label_provenance": "synthetic_proxy",
        "sample_count": count,
        "validation": "passed",
        "splits": {
            "train": [0, train_end],
            "validation": [train_end, validation_end],
            "test": [validation_end, count],
        },
    }
    output_manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
