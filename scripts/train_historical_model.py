"""Train, compare, and register a synthetic-proxy model candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from cogniflow_data.training import sha256
from preprocessing_api.features import FEATURE_NAMES

LABELS = ("LOW", "MEDIUM", "HIGH")


def evaluate(expected, predicted) -> dict:
    precision, recall, _, _ = precision_recall_fscore_support(expected, predicted, labels=LABELS, zero_division=0)
    return {"accuracy": accuracy_score(expected, predicted), "macro_f1": f1_score(expected, predicted, labels=LABELS, average="macro"), "per_class_precision": dict(zip(LABELS, precision.tolist())), "per_class_recall": dict(zip(LABELS, recall.tolist())), "confusion_matrix": confusion_matrix(expected, predicted, labels=LABELS).tolist()}


def train(dataset: Path, manifest_path: Path, output: Path, report_path: Path, *, tracking_uri: str, experiment: str, model_name: str) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if manifest["dataset_sha256"] != sha256(dataset) or manifest["feature_names"] != list(FEATURE_NAMES):
        raise ValueError("training manifest validation failed")
    frame = pd.read_json(dataset, lines=True).sort_values(["decision_time", "decision_id"])
    if len(frame) < 90:
        raise ValueError("at least 90 chronological samples are required")
    splits = manifest["splits"]
    train_frame = frame.iloc[slice(*splits["train"])]
    validation_frame = frame.iloc[slice(*splits["validation"])]
    test_frame = frame.iloc[slice(*splits["test"])]
    for name, part in (("train", train_frame), ("validation", validation_frame), ("test", test_frame)):
        if set(part["label"]) != set(LABELS):
            raise ValueError(f"{name} split lacks class coverage")
    models = {
        "dummy_majority": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": Pipeline([("scaler", StandardScaler()), ("classifier", LogisticRegression(max_iter=1000, random_state=42))]),
        "random_forest": RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced"),
    }
    validation = {}
    for name, candidate in models.items():
        candidate.fit(train_frame[list(FEATURE_NAMES)], train_frame["label"])
        validation[name] = evaluate(validation_frame["label"], candidate.predict(validation_frame[list(FEATURE_NAMES)]))
    selected_name = max(models, key=lambda name: (validation[name]["macro_f1"], name))
    selected = models[selected_name]
    test_metrics = evaluate(test_frame["label"], selected.predict(test_frame[list(FEATURE_NAMES)]))
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(selected, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    report = {"warning":"Metrics measure synthetic-proxy prediction, not real cognitive-load accuracy.","selected_model":selected_name,"validation":validation,"test":test_metrics,"class_distribution":frame["label"].value_counts().sort_index().to_dict(),"sample_counts":{"train":len(train_frame),"validation":len(validation_frame),"test":len(test_frame)},"model_sha256":digest,"dataset_manifest":manifest}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    run_ids = {}
    for name, candidate in models.items():
        with mlflow.start_run(run_name=name) as run:
            run_ids[name] = run.info.run_id
            params = {
                key: value
                for key, value in candidate.get_params(deep=False).items()
                if isinstance(value, (str, int, float, bool)) or value is None
            }
            mlflow.log_params(
                {
                    "model_type": name,
                    "dataset_sha256": manifest["dataset_sha256"],
                    "git_revision": manifest["git_revision"],
                    "feature_schema_version": "1.0",
                    "label_provenance": "synthetic_proxy",
                    "training_cutoff": manifest["training_cutoff"],
                    **params,
                }
            )
            mlflow.log_metrics(
                {
                    "validation_accuracy": validation[name]["accuracy"],
                    "validation_macro_f1": validation[name]["macro_f1"],
                }
            )
            if name != selected_name:
                continue
            mlflow.log_metrics({"test_accuracy":test_metrics["accuracy"],"test_macro_f1":test_metrics["macro_f1"]})
            mlflow.log_dict(report, "evaluation.json")
            mlflow.sklearn.log_model(
                selected,
                artifact_path="model",
                input_example=test_frame[list(FEATURE_NAMES)].head(2),
                skops_trusted_types=["sklearn.tree._tree.Tree"],
            )
            version = mlflow.register_model(f"runs:/{run.info.run_id}/model", model_name)
            client = mlflow.MlflowClient()
            client.set_model_version_tag(model_name, version.version, "approval_status", "candidate")
            client.set_model_version_tag(model_name, version.version, "model_sha256", digest)
            report.update({"mlflow_run_id":run.info.run_id,"model_version":version.version,"approval_status":"candidate"})
    report["mlflow_run_ids"] = run_ids
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("dataset", "manifest", "output", "report"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--tracking-uri", required=True)
    parser.add_argument("--experiment", default="cogniflow-module3-phase2")
    parser.add_argument("--model-name", default="cognitive-load-classifier-phase2")
    args = parser.parse_args()
    print(json.dumps(train(args.dataset,args.manifest,args.output,args.report,tracking_uri=args.tracking_uri,experiment=args.experiment,model_name=args.model_name)))


if __name__ == "__main__":
    main()
