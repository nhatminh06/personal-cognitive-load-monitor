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
from cogniflow_data.training import (
    candidate_models,
    evaluate_predictions,
    sha256_tree,
    split_training_frame,
    validate_training_manifest,
)
from preprocessing_api.features import FEATURE_NAMES

def train(dataset: Path, manifest_path: Path, output: Path, report_path: Path, *, tracking_uri: str, experiment: str, model_name: str) -> dict:
    manifest = json.loads(manifest_path.read_text())
    validate_training_manifest(manifest, dataset)
    frame = pd.read_json(dataset, lines=True)
    train_frame, validation_frame, test_frame = split_training_frame(frame, manifest)
    models = candidate_models()
    validation = {}
    for name, candidate in models.items():
        candidate.fit(train_frame[list(FEATURE_NAMES)], train_frame["label"])
        validation[name] = evaluate_predictions(validation_frame["label"], candidate.predict(validation_frame[list(FEATURE_NAMES)]))
    selected_name = max(models, key=lambda name: (validation[name]["macro_f1"], name))
    selected = models[selected_name]
    test_metrics = evaluate_predictions(test_frame["label"], selected.predict(test_frame[list(FEATURE_NAMES)]))
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(selected, output)
    export_digest = hashlib.sha256(output.read_bytes()).hexdigest()
    report = {"warning":"Metrics measure synthetic-proxy prediction, not real cognitive-load accuracy.","selected_model":selected_name,"validation":validation,"test":test_metrics,"class_distribution":frame["label"].value_counts().sort_index().to_dict(),"sample_counts":{"train":len(train_frame),"validation":len(validation_frame),"test":len(test_frame)},"exported_joblib_sha256":export_digest,"dataset_manifest":manifest}
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
            model_info = mlflow.sklearn.log_model(
                selected,
                artifact_path="model",
                input_example=test_frame[list(FEATURE_NAMES)].head(2),
                skops_trusted_types=["sklearn.tree._tree.Tree"],
            )
            version = mlflow.register_model(model_info.model_uri, model_name)
            registered_path = Path(
                mlflow.artifacts.download_artifacts(artifact_uri=version.source)
            )
            artifact_digest = sha256_tree(registered_path)
            client = mlflow.MlflowClient()
            client.set_model_version_tag(model_name, version.version, "approval_status", "candidate")
            client.set_model_version_tag(
                model_name, version.version, "registered_artifact_sha256", artifact_digest
            )
            client.set_model_version_tag(
                model_name, version.version, "exported_joblib_sha256", export_digest
            )
            report.update({"mlflow_run_id":run.info.run_id,"model_version":version.version,"approval_status":"candidate","registered_artifact_sha256":artifact_digest})
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
