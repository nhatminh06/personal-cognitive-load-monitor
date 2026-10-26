"""Generate bounded, deterministic Phase 2 synthetic features and labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from cogniflow_data.historical import HistoricalFeatureRow, SyntheticLabel, SYNTHETIC_DATASET
from preprocessing_api.features import FEATURE_NAMES, feature_vector


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=180)
    args = parser.parse_args()
    if not 90 <= args.samples <= 1000:
        raise ValueError("samples must be between 90 and 1000")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    features, labels = [], []
    names = ("LOW", "MEDIUM", "HIGH")
    for index in range(args.samples):
        latent = index % 3
        decision = base + timedelta(hours=index)
        focus = (150, 90, 35)[latent] + (index * 7 % 15)
        distraction = (15, 45, 100)[latent] + (index * 11 % 12)
        values = {"focus_minutes": focus, "distraction_minutes": distraction, "tasks_due": latent * 3 + index % 2, "hours_to_deadline": (96, 36, 8)[latent]}
        vector = feature_vector(values)
        features.append(HistoricalFeatureRow(
            decision_id=f"decision-{index:04d}", session_id=f"session-{index:04d}",
            event_id=UUID(int=index + 1), feature_schema_version="1.0", feature_names=FEATURE_NAMES,
            event_time=decision - timedelta(minutes=20), ingested_at=decision - timedelta(minutes=10),
            decision_time=decision, available_at=decision - timedelta(minutes=10),
            source_dataset=SYNTHETIC_DATASET, source_delta_version=None, source="phase2-fixture",
            kafka_topic="synthetic.fixture.v1", kafka_partition=0, kafka_offset=index,
            **dict(zip(FEATURE_NAMES, vector)),
        ))
        labels.append(SyntheticLabel(decision_id=f"decision-{index:04d}", label=names[latent], event_time=decision + timedelta(hours=1), available_at=decision + timedelta(hours=24)))
    args.features.parent.mkdir(parents=True, exist_ok=True)
    feature_bytes = "".join(row.model_dump_json() + "\n" for row in features).encode()
    label_bytes = "".join(row.model_dump_json() + "\n" for row in labels).encode()
    args.features.write_bytes(feature_bytes)
    args.labels.write_bytes(label_bytes)
    args.manifest.write_text(json.dumps({"feature_schema_version":"1.0","feature_names":list(FEATURE_NAMES),"source_dataset":SYNTHETIC_DATASET,"source_delta_versions":[],"sha256":hashlib.sha256(feature_bytes).hexdigest(),"row_count":len(features)}, indent=2, sort_keys=True)+"\n")


if __name__ == "__main__":
    main()
