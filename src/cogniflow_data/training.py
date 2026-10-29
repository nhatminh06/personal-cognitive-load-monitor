"""Validated historical training-set preparation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from preprocessing_api.features import FEATURE_NAMES

from .historical import HistoricalFeatureRow, SILVER_DATASET, SYNTHETIC_DATASET, SyntheticLabel

LABELS = ("LOW", "MEDIUM", "HIGH")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_tree(path: Path) -> str:
    """Hash artifact names and bytes so an MLflow model directory is immutable."""

    if not path.is_dir():
        raise ValueError(f"artifact directory is unavailable: {path}")
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise ValueError("artifact directory is empty")
    for item in files:
        relative = item.relative_to(path).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        payload = item.read_bytes()
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


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
    if not re.fullmatch(r"[0-9a-f]{40}", git_revision):
        raise ValueError("git revision must be a full commit SHA")

    features = load_jsonl(feature_path, HistoricalFeatureRow)
    labels = load_jsonl(label_path, SyntheticLabel)
    if manifest.get("row_count") not in (None, len(features)):
        raise ValueError("feature manifest row count mismatch")
    if any(feature.source_dataset != manifest.get("source_dataset") for feature in features):
        raise ValueError("feature manifest source lineage mismatch")
    versions = sorted(
        {feature.source_delta_version for feature in features if feature.source_delta_version is not None}
    )
    if versions != manifest.get("source_delta_versions", []):
        raise ValueError("feature manifest Delta lineage mismatch")
    feature_ids = [feature.decision_id for feature in features]
    if len(feature_ids) != len(set(feature_ids)):
        raise ValueError("duplicate feature decision_id")
    label_by_id: dict[str, SyntheticLabel] = {}
    for label in labels:
        if label.decision_id in label_by_id:
            raise ValueError(f"duplicate label decision_id: {label.decision_id}")
        label_by_id[label.decision_id] = label
    if set(label_by_id) - set(feature_ids):
        raise ValueError("feature and label decision identities are inconsistent")

    joined: list[dict[str, Any]] = []
    for feature in sorted(features, key=lambda row: (row.decision_time, row.decision_id)):
        if feature.decision_time > cutoff:
            raise ValueError("feature decision is after training cutoff")
        label = label_by_id.get(feature.decision_id)
        if label is None:
            raise ValueError(f"missing label: {feature.decision_id}")
        if label.available_at > cutoff:
            raise ValueError(f"label unavailable by cutoff: {feature.decision_id}")
        if label.event_time < feature.decision_time:
            raise ValueError(f"label event precedes decision: {feature.decision_id}")
        joined.append(
            {
                "decision_id": feature.decision_id,
                "decision_time": feature.decision_time.isoformat(),
                "feature_available_at": feature.available_at.isoformat(),
                "label_event_time": label.event_time.isoformat(),
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
        "label_availability_cutoff": cutoff.isoformat(),
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


def validate_training_manifest(manifest: dict[str, Any], dataset: Path) -> None:
    required = {
        "contract_version", "dataset_id", "dataset_sha256", "feature_input_sha256",
        "label_input_sha256", "feature_schema_version", "feature_names", "source_dataset",
        "source_delta_versions", "git_revision", "training_cutoff",
        "label_availability_cutoff", "label_provenance", "sample_count", "validation", "splits",
    }
    if not required <= manifest.keys():
        raise ValueError("training manifest lineage is incomplete")
    hashes = ("dataset_sha256", "feature_input_sha256", "label_input_sha256")
    if any(not re.fullmatch(r"[0-9a-f]{64}", str(manifest[key])) for key in hashes):
        raise ValueError("training manifest checksum is invalid")
    if manifest["dataset_sha256"] != sha256(dataset):
        raise ValueError("training dataset checksum mismatch")
    if (
        manifest["contract_version"] != "1.0"
        or manifest["feature_schema_version"] != "1.0"
        or manifest["feature_names"] != list(FEATURE_NAMES)
        or manifest["label_provenance"] != "synthetic_proxy"
        or manifest["validation"] != "passed"
        or not re.fullmatch(r"[0-9a-f]{40}", str(manifest["git_revision"]))
    ):
        raise ValueError("training manifest contract is invalid")
    source = manifest["source_dataset"]
    versions = manifest["source_delta_versions"]
    if source not in {SYNTHETIC_DATASET, SILVER_DATASET} or (
        source == SYNTHETIC_DATASET and versions
    ) or (
        source == SILVER_DATASET and not versions
    ):
        raise ValueError("training manifest source lineage is invalid")


def validate_training_frame(frame: Any, manifest: dict[str, Any]) -> None:
    count = len(frame)
    if manifest["sample_count"] != count:
        raise ValueError("training manifest sample count mismatch")
    expected_columns = {
        "decision_id", "decision_time", "feature_available_at", "label_event_time", "label_available_at",
        "label", "label_provenance", *FEATURE_NAMES,
    }
    if not expected_columns <= set(frame.columns):
        raise ValueError("training dataset schema is incomplete")
    if frame["decision_id"].duplicated().any():
        raise ValueError("training dataset contains duplicate decision IDs")
    ordered = frame.sort_values(["decision_time", "decision_id"]).index.tolist()
    if ordered != frame.index.tolist():
        raise ValueError("training dataset is not chronologically ordered")
    cutoff = datetime.fromisoformat(manifest["training_cutoff"])
    label_cutoff = datetime.fromisoformat(manifest["label_availability_cutoff"])
    if cutoff.tzinfo is None or label_cutoff != cutoff:
        raise ValueError("training manifest cutoff is invalid")
    def as_datetime(value: Any) -> datetime:
        return value.to_pydatetime() if hasattr(value, "to_pydatetime") else datetime.fromisoformat(value)

    decisions = frame["decision_time"].map(as_datetime)
    feature_times = frame["feature_available_at"].map(as_datetime)
    label_events = frame["label_event_time"].map(as_datetime)
    label_times = frame["label_available_at"].map(as_datetime)
    if any(feature > decision or decision > cutoff for feature, decision in zip(feature_times, decisions)):
        raise ValueError("training dataset has invalid feature timing")
    if any(
        event < decision or available < event or available > label_cutoff
        for event, decision, available in zip(label_events, decisions, label_times)
    ):
        raise ValueError("training dataset has unavailable labels")
    if set(frame["label_provenance"]) != {manifest["label_provenance"]}:
        raise ValueError("training dataset label lineage mismatch")
    if not all(math.isfinite(float(value)) for name in FEATURE_NAMES for value in frame[name]):
        raise ValueError("training dataset contains non-finite features")
    for row in frame.to_dict("records"):
        expected = (
            0.0
            if row["focus_minutes"] + row["distraction_minutes"] == 0
            else row["focus_minutes"] / (row["focus_minutes"] + row["distraction_minutes"]),
            0.0
            if row["focus_minutes"] + row["distraction_minutes"] == 0
            else row["distraction_minutes"] / (row["focus_minutes"] + row["distraction_minutes"]),
        )
        if any(
            not math.isclose(float(actual), wanted, abs_tol=1e-12)
            for actual, wanted in zip(
                (row["focus_ratio"], row["distraction_ratio"]), expected
            )
        ):
            raise ValueError("training dataset ratios are inconsistent")
    splits = manifest["splits"]
    try:
        train, validation, test = splits["train"], splits["validation"], splits["test"]
        if any(not isinstance(part, list) or len(part) != 2 for part in (train, validation, test)):
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("training split boundaries are invalid") from error
    if not (
        train == [0, train[1]]
        and 0 < train[1] == validation[0] < validation[1] == test[0] < test[1] == count
    ):
        raise ValueError("training split boundaries are invalid")


def split_training_frame(frame: Any, manifest: dict[str, Any]) -> tuple[Any, Any, Any]:
    """Validate once, then return immutable chronological train/validation/test slices."""

    if len(frame) < 90:
        raise ValueError("at least 90 chronological samples are required")
    validate_training_frame(frame, manifest)
    splits = manifest["splits"]
    parts = tuple(frame.iloc[slice(*splits[name])].copy() for name in ("train", "validation", "test"))
    for name, part in zip(("train", "validation", "test"), parts):
        if set(part["label"]) != set(LABELS):
            raise ValueError(f"{name} split lacks class coverage")
    return parts


def candidate_models(random_seed: int = 42) -> dict[str, Any]:
    return {
        "dummy_majority": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                ("classifier", LogisticRegression(max_iter=1000, random_state=random_seed)),
            ]
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=200, random_state=random_seed, class_weight="balanced"
        ),
    }


def evaluate_predictions(expected: Any, predicted: Any) -> dict[str, Any]:
    precision, recall, _, _ = precision_recall_fscore_support(
        expected, predicted, labels=LABELS, zero_division=0
    )
    return {
        "accuracy": accuracy_score(expected, predicted),
        "macro_f1": f1_score(expected, predicted, labels=LABELS, average="macro"),
        "per_class_precision": dict(zip(LABELS, precision.tolist())),
        "per_class_recall": dict(zip(LABELS, recall.tolist())),
        "confusion_matrix": confusion_matrix(expected, predicted, labels=LABELS).tolist(),
    }
