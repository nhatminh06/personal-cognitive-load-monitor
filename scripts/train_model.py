"""Train and register a simple cognitive-load classifier with MLflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_generator import generate_sample_data
from preprocessing_api.features import FEATURE_COLUMNS, LABEL_MAP


def load_params() -> dict:
    """Load params.yaml so DVC's params: tracking and this script agree on values.

    Falls back to the values this script has always used if params.yaml is
    missing, so `python scripts/train_model.py` still works standalone.
    """

    params_path = PROJECT_ROOT / "params.yaml"
    if not params_path.exists():
        return {}
    return yaml.safe_load(params_path.read_text(encoding="utf-8")) or {}


def parse_args() -> argparse.Namespace:
    params = load_params()
    data_params = params.get("data", {})
    model_params = params.get("model", {})
    train_params = params.get("train", {})

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=data_params.get("raw_path", "data/raw/sample_data.csv"))
    parser.add_argument("--output", default=model_params.get("output_path", "models/cognitive_load_model.joblib"))
    parser.add_argument("--experiment-name", default=model_params.get("experiment_name", "personal-cognitive-load-monitor"))
    parser.add_argument("--registered-model-name", default=model_params.get("registered_model_name", "cognitive-load-classifier"))
    parser.add_argument("--test-size", type=float, default=train_params.get("test_size", 0.2))
    parser.add_argument("--random-state", type=int, default=train_params.get("random_state", 42))
    parser.add_argument("--n-estimators", type=int, default=train_params.get("n_estimators", 200))
    return parser.parse_args()


def load_or_generate(input_path: Path) -> pd.DataFrame:
    if not input_path.exists():
        params = load_params().get("data", {})
        generate_sample_data(
            n_samples=params.get("n_samples", 500),
            output_path=input_path,
            seed=params.get("seed", 42),
            reference_date=params.get("reference_date"),
        )
    return pd.read_csv(input_path)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    total_time = data["focus_minutes"] + data["distraction_minutes"]
    data["focus_ratio"] = (data["focus_minutes"] / total_time.replace(0, pd.NA)).fillna(0.0)
    data["distraction_ratio"] = (data["distraction_minutes"] / total_time.replace(0, pd.NA)).fillna(0.0)
    return data


def _git_commit_sha() -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def main() -> None:
    args = parse_args()
    input_path = PROJECT_ROOT / args.input
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = add_features(load_or_generate(input_path))
    if df["cognitive_load_level"].isna().any():
        raise ValueError("cognitive_load_level contains missing labels; refusing to train on incomplete data.")
    unknown_labels = set(df["cognitive_load_level"].unique()) - set(LABEL_MAP)
    if unknown_labels:
        raise ValueError(f"Unknown cognitive_load_level values not in {list(LABEL_MAP)}: {unknown_labels}")

    y = df["cognitive_load_level"].map(LABEL_MAP)
    x = df[FEATURE_COLUMNS]
    class_distribution = df["cognitive_load_level"].value_counts().to_dict()

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=args.test_size,
        random_state=args.random_state,
        stratify=y,
    )

    # Majority-class baseline: the trained model must clear this bar to prove it
    # is learning anything beyond always guessing the most common class.
    majority_class = y_train.mode().iloc[0]
    baseline_accuracy = accuracy_score(y_test, [majority_class] * len(y_test))

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=args.n_estimators, random_state=args.random_state, class_weight="balanced"
                ),
            ),
        ]
    )
    pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_test)
    accuracy = accuracy_score(y_test, predictions)
    report = classification_report(y_test, predictions, output_dict=True, zero_division=0)
    conf_matrix = confusion_matrix(y_test, predictions).tolist()

    joblib.dump(pipeline, output_path)

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    metrics = {
        "accuracy": accuracy,
        "baseline_majority_class_accuracy": baseline_accuracy,
        "macro_f1": report["macro avg"]["f1-score"],
        "weighted_f1": report["weighted avg"]["f1-score"],
        "per_class": {
            label: report[str(class_index)]
            for label, class_index in LABEL_MAP.items()
            if str(class_index) in report
        },
        "confusion_matrix": conf_matrix,
        "class_distribution": {str(k): int(v) for k, v in class_distribution.items()},
        "train_size": len(x_train),
        "test_size": len(x_test),
        "git_commit": _git_commit_sha(),
    }
    (reports_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    train_df = x_train.copy()
    train_df["cognitive_load_level"] = y_train.values
    test_df = x_test.copy()
    test_df["cognitive_load_level"] = y_test.values
    train_df.to_csv(processed_dir / "train.csv", index=False)
    test_df.to_csv(processed_dir / "test.csv", index=False)

    try:
        import mlflow
        import mlflow.sklearn

        mlflow.set_experiment(args.experiment_name)
        with mlflow.start_run() as run:
            mlflow.log_param("model_type", "RandomForestClassifier")
            mlflow.log_param("n_estimators", args.n_estimators)
            mlflow.log_param("random_state", args.random_state)
            mlflow.log_param("test_size", args.test_size)
            mlflow.log_param("feature_columns", FEATURE_COLUMNS)
            git_commit = _git_commit_sha()
            if git_commit:
                mlflow.set_tag("git_commit", git_commit)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric("baseline_majority_class_accuracy", baseline_accuracy)
            mlflow.log_metric("macro_f1", metrics["macro_f1"])
            mlflow.log_metric("weighted_f1", metrics["weighted_f1"])
            mlflow.log_artifact(str(output_path), artifact_path="model")
            mlflow.sklearn.log_model(
                sk_model=pipeline,
                artifact_path="sklearn-model",
                registered_model_name=args.registered_model_name,
                input_example=x_test.head(2),
            )
            print(f"MLflow run_id={run.info.run_id}")
    except Exception as exc:
        print(f"WARNING: MLflow logging skipped: {exc}")

    print(f"Saved model to {output_path}")
    print(f"Accuracy: {accuracy:.3f} (majority-class baseline: {baseline_accuracy:.3f})")
    print(f"Class distribution (train+test source data): {class_distribution}")
    print(classification_report(y_test, predictions, zero_division=0))


if __name__ == "__main__":
    main()
