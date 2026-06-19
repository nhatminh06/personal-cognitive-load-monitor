"""Train and register a simple cognitive-load classifier with MLflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_generator import generate_sample_data

FEATURE_COLUMNS = [
    "focus_minutes",
    "distraction_minutes",
    "tasks_due",
    "hours_to_deadline",
    "focus_ratio",
    "distraction_ratio",
]

LABEL_MAP = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/raw/sample_data.csv")
    parser.add_argument("--output", default="models/cognitive_load_model.joblib")
    parser.add_argument("--experiment-name", default="personal-cognitive-load-monitor")
    parser.add_argument("--registered-model-name", default="cognitive-load-classifier")
    return parser.parse_args()


def load_or_generate(input_path: Path) -> pd.DataFrame:
    if not input_path.exists():
        generate_sample_data(n_samples=500, output_path=input_path)
    return pd.read_csv(input_path)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy()
    total_time = data["focus_minutes"] + data["distraction_minutes"]
    data["focus_ratio"] = (data["focus_minutes"] / total_time.replace(0, pd.NA)).fillna(0.0)
    data["distraction_ratio"] = (data["distraction_minutes"] / total_time.replace(0, pd.NA)).fillna(0.0)
    return data


def main() -> None:
    args = parse_args()
    input_path = PROJECT_ROOT / args.input
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = add_features(load_or_generate(input_path))
    y = df["cognitive_load_level"].map(LABEL_MAP)
    x = df[FEATURE_COLUMNS]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("classifier", RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")),
        ]
    )
    pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_test)
    accuracy = accuracy_score(y_test, predictions)

    joblib.dump(pipeline, output_path)

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "metrics.json").write_text(json.dumps({"accuracy": accuracy}, indent=2), encoding="utf-8")

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
            mlflow.log_param("n_estimators", 200)
            mlflow.log_metric("accuracy", accuracy)
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
    print(f"Accuracy: {accuracy:.3f}")
    print(classification_report(y_test, predictions))


if __name__ == "__main__":
    main()
