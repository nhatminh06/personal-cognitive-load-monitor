"""Train and compare isolated Module I synthetic-proxy candidates."""

from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cogniflow_data.training import candidate_models, evaluate_predictions  # noqa: E402
from data_generator import generate_sample_data  # noqa: E402
from preprocessing_api.features import FEATURE_NAMES, feature_vector  # noqa: E402

FEATURE_COLUMNS = list(FEATURE_NAMES)
LABELS = ("LOW", "MEDIUM", "HIGH")
CANDIDATE_ORDER = ("dummy_majority", "logistic_regression", "random_forest")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/raw/sample_data.csv"))
    parser.add_argument("--output", type=Path, default=Path("models/cognitive_load_model.joblib"))
    parser.add_argument("--report", type=Path, default=Path("reports/metrics.json"))
    parser.add_argument("--train-output", type=Path, default=Path("data/processed/train.csv"))
    parser.add_argument("--validation-output", type=Path, default=Path("data/processed/validation.csv"))
    parser.add_argument("--audit-output", type=Path, default=Path("data/processed/previously_observed.csv"))
    parser.add_argument("--train-fraction", type=float, default=0.6)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--random-seed", type=int, default=42)
    parser.add_argument("--experiment-name", default="cogniflow-module1-engineering-candidates")
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI", ""))
    parser.add_argument("--generate-if-missing", action="store_true")
    return parser.parse_args()


def load_dataset(input_path: Path, *, generate_if_missing: bool = False) -> pd.DataFrame:
    if not input_path.exists():
        if not generate_if_missing:
            raise FileNotFoundError(
                f"training input is missing: {input_path}; run the DVC generate_data stage"
            )
        generate_sample_data(n_samples=500, output_path=input_path)
    return pd.read_csv(input_path)


def add_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    vectors = data.apply(lambda row: feature_vector(row), axis=1, result_type="expand")
    vectors.columns = FEATURE_COLUMNS
    data[FEATURE_COLUMNS] = vectors
    return data


def _partition_digest(frame: pd.DataFrame) -> str:
    return hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode()).hexdigest()


def split_chronologically(
    raw: pd.DataFrame,
    *,
    train_fraction: float,
    validation_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    required = {"date", "cognitive_load_level", "label_provenance", *FEATURE_COLUMNS[:4]}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if raw.empty:
        raise ValueError("training dataset is empty")
    if raw.duplicated().any():
        raise ValueError("training dataset contains duplicate records")
    if set(raw["label_provenance"]) != {"synthetic_proxy"}:
        raise ValueError("training data must explicitly use synthetic_proxy labels")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("split fractions must leave a previously observed partition")

    data = raw.copy()
    try:
        data["_split_time"] = pd.to_datetime(
            data["date"], utc=True, errors="raise", format="mixed"
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("date values must be valid timestamps") from exc
    data = data.sort_values(
        ["_split_time", *FEATURE_COLUMNS[:4], "cognitive_load_level"], kind="stable"
    ).reset_index(drop=True)
    labels = data["cognitive_load_level"]
    if labels.isna().any() or not set(labels) <= set(LABELS):
        raise ValueError("cognitive_load_level contains an unsupported class")

    unique_times = data["_split_time"].drop_duplicates().tolist()
    train_end = int(len(unique_times) * train_fraction)
    validation_end = int(len(unique_times) * (train_fraction + validation_fraction))
    if not 0 < train_end < validation_end < len(unique_times):
        raise ValueError("dataset has too few timestamp groups for three partitions")
    groups = (
        set(unique_times[:train_end]),
        set(unique_times[train_end:validation_end]),
        set(unique_times[validation_end:]),
    )
    parts = tuple(data[data["_split_time"].isin(group)].copy() for group in groups)
    names = ("train", "validation", "previously_observed")
    for name, part in zip(names, parts):
        missing_classes = set(LABELS) - set(part["cognitive_load_level"])
        if missing_classes:
            raise ValueError(f"{name} partition lacks classes: {sorted(missing_classes)}")
    if not (
        parts[0]["_split_time"].max() < parts[1]["_split_time"].min()
        and parts[1]["_split_time"].max() < parts[2]["_split_time"].min()
    ):
        raise ValueError("partition timestamps overlap")
    for identity in ("subject_id", "session_id"):
        if identity not in data.columns:
            continue
        if data[identity].isna().any():
            raise ValueError(f"{identity} contains null values")
        sets = [set(part[identity]) for part in parts]
        if any(sets[left] & sets[right] for left, right in ((0, 1), (0, 2), (1, 2))):
            raise ValueError(f"{identity} overlaps partitions")

    split_report = {
        "method": "chronological_timestamp_groups",
        "train_fraction": train_fraction,
        "validation_fraction": validation_fraction,
        "selection_partition": "validation",
        "final_partition_status": "previously_observed_not_independent",
        "duplicate_record_count": 0,
        "duplicate_timestamp_row_count": int(data["_split_time"].duplicated(keep=False).sum()),
        "group_overlap_check": "unavailable_no_identifiers"
        if not {"subject_id", "session_id"} & set(data.columns)
        else "passed",
        "partitions": {
            name: {
                "row_count": len(part),
                "timestamp_group_count": int(part["_split_time"].nunique()),
                "start": part["_split_time"].min().isoformat(),
                "end": part["_split_time"].max().isoformat(),
                "class_counts": {
                    label: int((part["cognitive_load_level"] == label).sum())
                    for label in LABELS
                },
                "membership_sha256": _partition_digest(
                    part[["date", *FEATURE_COLUMNS[:4], "cognitive_load_level"]]
                ),
            }
            for name, part in zip(names, parts)
        },
    }
    return (*parts, split_report)


def select_candidate(validation: dict[str, dict[str, Any]]) -> str:
    if set(validation) != set(CANDIDATE_ORDER):
        raise ValueError("candidate results are incomplete")
    order = {name: index for index, name in enumerate(CANDIDATE_ORDER)}
    return min(
        CANDIDATE_ORDER,
        key=lambda name: (
            -float(validation[name]["macro_f1"]),
            -float(validation[name]["accuracy"]),
            order[name],
        ),
    )


def _git_revision() -> str:
    revision = os.getenv("GITHUB_SHA", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("unable to determine a full Git revision")
    return revision


def _lineage(input_path: Path, split_report: dict[str, Any], random_seed: int) -> dict[str, Any]:
    configuration = {
        "train_fraction": split_report["train_fraction"],
        "validation_fraction": split_report["validation_fraction"],
        "random_seed": random_seed,
        "selection_metric": "validation_macro_f1",
        "tie_break": list(CANDIDATE_ORDER),
    }
    return {
        "dataset_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "split_sha256": hashlib.sha256(
            json.dumps(split_report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "git_revision": _git_revision(),
        "git_dirty": bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=PROJECT_ROOT, check=True,
                capture_output=True, text=True,
            ).stdout
        ),
        "dvc_pipeline_sha256": hashlib.sha256((PROJECT_ROOT / "dvc.yaml").read_bytes()).hexdigest(),
        "training_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "candidate_code_sha256": hashlib.sha256(
            (PROJECT_ROOT / "src/cogniflow_data/training.py").read_bytes()
        ).hexdigest(),
        "feature_code_sha256": hashlib.sha256(
            (PROJECT_ROOT / "src/preprocessing_api/features.py").read_bytes()
        ).hexdigest(),
        "configuration": configuration,
        "configuration_sha256": hashlib.sha256(
            json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "feature_schema_version": "1.0",
        "feature_names": FEATURE_COLUMNS,
        "label_provenance": "synthetic_proxy",
        "random_seed": random_seed,
        "dependencies": {
            "python": sys.version.split()[0],
            **{name: version(name) for name in ("mlflow", "numpy", "pandas", "scikit-learn")},
        },
    }


def _model_params(model: Any) -> dict[str, str | int | float | bool]:
    return {
        key: value for key, value in model.get_params(deep=True).items()
        if isinstance(value, (str, int, float, bool)) and len(str(value)) <= 500
    }


def _set_experiment(mlflow: Any, tracking_uri: str, experiment_name: str) -> None:
    if tracking_uri.startswith("sqlite:///"):
        database = Path(tracking_uri.removeprefix("sqlite:///"))
        if not database.is_absolute():
            database = PROJECT_ROOT / database
        client = mlflow.MlflowClient()
        experiment = client.get_experiment_by_name(experiment_name)
        experiment_id = (
            experiment.experiment_id
            if experiment is not None
            else client.create_experiment(
                experiment_name,
                artifact_location=(database.parent / "mlartifacts").resolve().as_uri(),
            )
        )
        mlflow.set_experiment(experiment_id=experiment_id)
        return
    mlflow.set_experiment(experiment_name)


def train(
    input_path: Path, output_path: Path, report_path: Path,
    train_output: Path, validation_output: Path, audit_output: Path,
    *, train_fraction: float, validation_fraction: float, random_seed: int,
    tracking_uri: str, experiment_name: str, generate_if_missing: bool = False,
) -> dict[str, Any]:
    raw = load_dataset(input_path, generate_if_missing=generate_if_missing)
    train_raw, validation_raw, audit_raw, split_report = split_chronologically(
        raw, train_fraction=train_fraction, validation_fraction=validation_fraction
    )
    parts = tuple(add_features(part) for part in (train_raw, validation_raw, audit_raw))
    train_frame, validation_frame, audit_frame = parts
    models = candidate_models(random_seed)
    validation: dict[str, dict[str, Any]] = {}
    for name in CANDIDATE_ORDER:
        model = models[name]
        model.fit(train_frame[FEATURE_COLUMNS], train_frame["cognitive_load_level"])
        validation[name] = evaluate_predictions(
            validation_frame["cognitive_load_level"],
            model.predict(validation_frame[FEATURE_COLUMNS]),
        )
    selected_name = select_candidate(validation)
    selected = models[selected_name]
    audit_metrics = evaluate_predictions(
        audit_frame["cognitive_load_level"], selected.predict(audit_frame[FEATURE_COLUMNS])
    )

    for path, frame in zip((train_output, validation_output, audit_output), parts):
        path.parent.mkdir(parents=True, exist_ok=True)
        frame[[*FEATURE_COLUMNS, "cognitive_load_level"]].to_csv(path, index=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(selected, output_path)
    lineage = _lineage(input_path, split_report, random_seed)
    report: dict[str, Any] = {
        "contract_version": "2.0",
        "validation_scope": "synthetic_proxy_engineering_only",
        "warning": "Metrics measure synthetic-rule fidelity, not real cognitive-load validity.",
        "selected_model": selected_name,
        "selection_rule": {
            "primary": "validation_macro_f1_desc",
            "secondary": "validation_accuracy_desc",
            "tie_break": list(CANDIDATE_ORDER),
        },
        "split": split_report,
        "lineage": lineage,
        "models": {
            name: {"parameters": _model_params(models[name]), "validation": validation[name]}
            for name in CANDIDATE_ORDER
        },
        "previously_observed_audit": {
            "status": "not_independent_and_not_used_for_selection",
            "selected_model_metrics": audit_metrics,
        },
        "exported_joblib_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
    }

    if tracking_uri:
        import mlflow
        import mlflow.sklearn

        mlflow.set_tracking_uri(tracking_uri)
        _set_experiment(mlflow, tracking_uri, experiment_name)
        for name in CANDIDATE_ORDER:
            with mlflow.start_run(run_name=name):
                mlflow.log_params(
                    {
                        "model_type": name,
                        "dataset_sha256": lineage["dataset_sha256"],
                        "split_sha256": lineage["split_sha256"],
                        "git_revision": lineage["git_revision"],
                        "dvc_pipeline_sha256": lineage["dvc_pipeline_sha256"],
                        "configuration_sha256": lineage["configuration_sha256"],
                        "training_code_sha256": lineage["training_code_sha256"],
                        "candidate_code_sha256": lineage["candidate_code_sha256"],
                        "feature_code_sha256": lineage["feature_code_sha256"],
                        "git_dirty": lineage["git_dirty"],
                        "feature_schema_version": "1.0",
                        "feature_names": json.dumps(FEATURE_COLUMNS),
                        "label_provenance": "synthetic_proxy",
                        "validation_scope": report["validation_scope"],
                        "random_seed": random_seed,
                        "selection_metric": "validation_macro_f1",
                        **_model_params(models[name]),
                    }
                )
                mlflow.log_metrics({
                    "validation_accuracy": validation[name]["accuracy"],
                    "validation_macro_f1": validation[name]["macro_f1"],
                })
                mlflow.log_dict({"split": split_report, "lineage": lineage}, "lineage.json")
                mlflow.sklearn.log_model(
                    models[name], artifact_path="model",
                    input_example=validation_frame[FEATURE_COLUMNS].head(2),
                    skops_trusted_types=["sklearn.tree._tree.Tree"],
                )
                if name == selected_name:
                    mlflow.log_dict(report, "evaluation.json")
        report["mlflow_experiment"] = experiment_name
        report["registry_mutation"] = "none"
    else:
        report["mlflow_status"] = "not_configured"
        if os.getenv("REQUIRE_MLFLOW", "false").lower() == "true":
            raise RuntimeError("MLflow tracking URI is required")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> None:
    args = parse_args()
    report = train(
        PROJECT_ROOT / args.input, PROJECT_ROOT / args.output, PROJECT_ROOT / args.report,
        PROJECT_ROOT / args.train_output, PROJECT_ROOT / args.validation_output,
        PROJECT_ROOT / args.audit_output, train_fraction=args.train_fraction,
        validation_fraction=args.validation_fraction, random_seed=args.random_seed,
        tracking_uri=args.tracking_uri, experiment_name=args.experiment_name,
        generate_if_missing=args.generate_if_missing,
    )
    print(json.dumps({"selected_model": report["selected_model"]}, sort_keys=True))


if __name__ == "__main__":
    main()
