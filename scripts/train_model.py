"""Train and register a simple cognitive-load classifier with MLflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_generator import generate_sample_data  # noqa: E402
from preprocessing_api.features import FEATURE_NAMES, feature_vector  # noqa: E402

FEATURE_COLUMNS = list(FEATURE_NAMES)

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
    vectors = data.apply(lambda row: feature_vector(row), axis=1, result_type="expand")
    vectors.columns = FEATURE_COLUMNS
    data[FEATURE_COLUMNS] = vectors
    return data


def metrics(y_true, predictions) -> dict:
    return {
        "accuracy": accuracy_score(y_true, predictions),
        "macro_f1": f1_score(y_true, predictions, average="macro"),
        "per_class_recall": recall_score(y_true, predictions, average=None, labels=[0, 1, 2]).tolist(),
        "confusion_matrix": confusion_matrix(y_true, predictions, labels=[0, 1, 2]).tolist(),
    }


def main() -> None:
    args = parse_args()
    input_path = PROJECT_ROOT / args.input
    output_path = PROJECT_ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw = load_or_generate(input_path)
    required = {"date", "cognitive_load_level", "label_provenance", *FEATURE_COLUMNS[:4]}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if set(raw["label_provenance"]) != {"synthetic_proxy"}:
        raise ValueError("Training data must explicitly use synthetic_proxy labels")
    df = add_features(raw).sort_values("date").reset_index(drop=True)
    y = df["cognitive_load_level"].map(LABEL_MAP)
    if y.isna().any():
        raise ValueError("Unknown cognitive_load_level value")
    x = df[FEATURE_COLUMNS]
    split = int(len(df) * 0.8)
    x_train, x_test, y_train, y_test = x.iloc[:split], x.iloc[split:], y.iloc[:split], y.iloc[split:]

    pipeline = Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            ("classifier", RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")),
        ]
    )
    candidates = {
        "dummy_majority": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": Pipeline([("scaler", StandardScaler()), ("classifier", LogisticRegression(max_iter=1000, random_state=42))]),
        "random_forest": pipeline,
    }
    results = {"rule_baseline": metrics(y_test, y_test)}
    for name, candidate in candidates.items():
        candidate.fit(x_train, y_train)
        results[name] = metrics(y_test, candidate.predict(x_test))
    pipeline.fit(x_train, y_train)
    predictions = pipeline.predict(x_test)
    accuracy = results["random_forest"]["accuracy"]

    joblib.dump(pipeline, output_path)

    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    dataset_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    report = {
        "label_provenance": "synthetic_proxy",
        "dataset_sha256": dataset_hash,
        "split": "chronological_80_20",
        "feature_names": FEATURE_COLUMNS,
        "models": results,
        "warning": "Scores measure fidelity to synthetic rules, not real cognitive load validity.",
    }
    (reports_dir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

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
            mlflow.log_param("label_provenance", "synthetic_proxy")
            mlflow.log_param("dataset_sha256", dataset_hash)
            mlflow.log_metric("accuracy", accuracy)
            mlflow.log_metric("macro_f1", results["random_forest"]["macro_f1"])
            mlflow.log_dict(report, "evaluation.json")
            mlflow.log_artifact(str(output_path), artifact_path="model")
            mlflow.sklearn.log_model(
                sk_model=pipeline,
                artifact_path="sklearn-model",
                registered_model_name=args.registered_model_name,
                input_example=x_test.head(2),
            )
            print(f"MLflow run_id={run.info.run_id}")
    except Exception as exc:
        if __import__("os").getenv("REQUIRE_MLFLOW", "false").lower() == "true":
            raise
        print(f"WARNING: MLflow logging skipped: {exc}")

    print(f"Saved model to {output_path}")
    print(f"Accuracy: {accuracy:.3f}")
    print(classification_report(y_test, predictions))


if __name__ == "__main__":
    main()
