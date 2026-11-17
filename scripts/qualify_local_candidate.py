"""Assert-based, offline candidate review; never writes approval or serving packages."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

import mlflow
import pandas as pd
import skops.io
import yaml

from cogniflow_data.training import (
    GROUP_SPLIT, feature_group, select_candidate, split_identity,
    candidate_models, evaluate_predictions, prepare_training_dataset, sha256,
    sha256_tree, split_training_frame, validate_training_manifest,
)
from cogniflow_kserve.predictor import CogniFlowPredictor
from preprocessing_api.features import FEATURE_NAMES
from preprocessing_api.model_client import _SKOPS_TRUSTED_TYPES
from scripts.generate_training_fixture import generate_fixture
from scripts.package_approved_model import package_approved_model


def qualify(root: Path, model_name: str, model_version: str, run_id: str, digest: str) -> dict:
    if not __debug__:
        raise RuntimeError("qualification requires assertions; do not use python -O")
    root = root.resolve()
    assert (root / "mlflow.db").is_file(), "local registry is missing"
    mlflow.set_tracking_uri("sqlite:///" + str(root / "mlflow.db"))
    mlflow.set_registry_uri("sqlite:///" + str(root / "mlflow.db"))
    client = mlflow.MlflowClient()
    candidate = client.get_model_version(model_name, model_version)
    assert (candidate.name, str(candidate.version), candidate.run_id) == (
        model_name, model_version, run_id
    ), "registry identity mismatch"
    assert candidate.tags.get("approval_status") == "candidate", "not an unapproved candidate"
    assert candidate.tags.get("registered_artifact_sha256") == digest, "registry digest mismatch"
    assert isinstance(candidate.source, str) and candidate.source.startswith("models:/m-"), "expected a local logged-model identity"
    logged = client.get_logged_model(candidate.source.removeprefix("models:/"))
    assert logged.artifact_location.startswith(root.as_uri() + "/"), "nonlocal artifact location"
    artifact = Path(mlflow.artifacts.download_artifacts(artifact_uri=candidate.source))
    assert not any(p.is_symlink() for p in artifact.rglob("*")), "symlink in artifact"
    assert sha256_tree(artifact) == digest, "artifact tree digest mismatch"
    metadata = yaml.safe_load((artifact / "MLmodel").read_text())
    assert [item["name"] for item in json.loads(metadata["signature"]["inputs"])] == list(FEATURE_NAMES)
    assert metadata["flavors"]["sklearn"]["serialization_format"] == "skops"
    assert metadata["flavors"]["sklearn"]["pickled_model"] == "model.skops"
    model_path = artifact / "model.skops"
    model_digest = sha256(model_path)
    untrusted = skops.io.get_untrusted_types(file=model_path)
    assert set(untrusted) <= set(_SKOPS_TRUSTED_TYPES), "unreviewed skops types"

    manifest = json.loads((root / "dataset.manifest.json").read_text())
    report = json.loads((root / "evaluation.json").read_text())
    validate_training_manifest(manifest, root / "dataset.jsonl")
    assert sha256(root / "features.jsonl") == manifest["feature_input_sha256"]
    assert sha256(root / "labels.jsonl") == manifest["label_input_sha256"]
    assert report["dataset_manifest"] == manifest
    assert report["registered_artifact_sha256"] == digest
    assert report["mlflow_run_id"] == run_id
    params = client.get_run(run_id).data.params
    for key in ("dataset_sha256", "git_revision", "feature_schema_version", "label_provenance"):
        assert params[key] == manifest[key], f"run lineage mismatch: {key}"
    frame = pd.read_json(root / "dataset.jsonl", lines=True)
    train, validation, test = split_training_frame(frame, manifest)
    rows = (root / "dataset.jsonl").read_bytes().splitlines(keepends=True)
    splits = {}
    for name, membership in manifest["splits"].items():
        grouped = manifest.get("split_protocol") == GROUP_SPLIT
        payload = b"".join(rows[index] for index in membership) if grouped else b"".join(rows[slice(*membership)])
        splits[name] = {"row_indices" if grouped else "bounds": membership,
                        "sha256": hashlib.sha256(payload).hexdigest()}
    train_vectors = set(map(tuple, train[list(FEATURE_NAMES)].values.tolist()))
    overlap = {
        name: sum(tuple(row) in train_vectors for row in part[list(FEATURE_NAMES)].values.tolist())
        for name, part in (("validation", validation), ("test", test))
    }

    with tempfile.TemporaryDirectory() as temporary:
        scratch = Path(temporary)
        generate_fixture(scratch / "features", scratch / "labels", scratch / "features.json",
                         manifest["sample_count"])
        prepare_training_dataset(
            scratch / "features", scratch / "features.json", scratch / "labels",
            scratch / "dataset", scratch / "manifest",
            training_cutoff=datetime.fromisoformat(manifest["training_cutoff"]),
            git_revision=manifest["git_revision"],
            split_protocol=manifest.get("split_protocol", "chronological_v1"),
        )
        assert sha256(scratch / "dataset") == manifest["dataset_sha256"], "regeneration mismatch"
        assert sha256(scratch / "features") == manifest["feature_input_sha256"]
        assert sha256(scratch / "labels") == manifest["label_input_sha256"]
        try:
            package_approved_model(model_name, model_version, run_id, digest, scratch / "package")
        except ValueError as error:
            assert str(error) == "model version is not explicitly approved"
        else:
            raise AssertionError("unapproved candidate was packaged")
        assert not (scratch / "package").exists()

        # Candidate-only validator is injected for this offline check, never a serving manifest.
        def verify_candidate(path: Path, actual_digest: str) -> dict:
            if actual_digest != model_digest:
                raise ValueError("candidate model digest mismatch")
            return {"approval_status": "candidate", "model_name": model_name,
                    "model_version": model_version}

        with patch.dict(os.environ, {"MODEL_PATH": str(model_path)}):
            predictor = CogniFlowPredictor(manifest_validator=verify_candidate)
            assert predictor.load()
            for partition, expected in ((validation, report["validation"][report["selected_model"]]),
                                        (test, report["test"])):
                payload = {"feature_names": list(FEATURE_NAMES),
                           "instances": partition[list(FEATURE_NAMES)].values.tolist()}
                predicted = predictor.predict(payload)["predictions"]
                assert evaluate_predictions(partition["label"], predicted) == expected
                assert set(predicted) == {"LOW", "MEDIUM", "HIGH"}
            assert CogniFlowPredictor(manifest_validator=verify_candidate).load()
            corrupt = scratch / "corrupt.skops"
            corrupt.write_bytes(model_path.read_bytes() + b"corruption")
            for path in (corrupt, scratch / "missing.skops"):
                with patch.dict(os.environ, {"MODEL_PATH": str(path)}):
                    try:
                        predictor.load()
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("invalid artifact loaded")
                    assert not predictor.ready and predictor.model is None
            assert predictor.load()

    reproduced = {}
    for name, model in candidate_models().items():
        model.fit(train[list(FEATURE_NAMES)], train["label"])
        reproduced[name] = evaluate_predictions(
            validation["label"], model.predict(validation[list(FEATURE_NAMES)])
        )
    assert reproduced == report["validation"], "fresh-fit validation mismatch"
    if manifest.get("split_protocol") == GROUP_SPLIT:
        assert params["split_sha256"] == split_identity(manifest)
        assert report["selected_model"] == select_candidate(reproduced)
        groups = [set(part.apply(lambda row: feature_group(row.to_dict()), axis=1))
                  for part in (train, validation, test)]
        assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    return {
        "partition_statistics": {
            name: {"rows": len(part), "classes": part["label"].value_counts().sort_index().to_dict(),
                   "groups": len({feature_group(row) for row in part.to_dict("records")})}
            for name, part in (("train", train), ("validation", validation), ("test", test))
        },
        "split_sha256": split_identity(manifest),
        "selection_policy": report.get("selection_policy", "legacy_macro_f1_then_name"),
        "status": "PASS_LOCAL_CANDIDATE_ONLY", "approval_status": "candidate",
        "kserve_runtime": "NOT_RUN", "production_packaging": "REJECTED_UNAPPROVED",
        "model_name": model_name, "model_version": model_version, "run_id": run_id,
        "registered_source": candidate.source, "registered_artifact_sha256": digest,
        "model_skops_sha256": model_digest, "dataset_manifest": manifest,
        "partition_identity": splits, "evaluation_sha256": sha256(root / "evaluation.json"),
        "feature_rows_also_in_train": overlap,
        "selected_model": report["selected_model"], "validation": reproduced,
        "test": report["test"], "sample_counts": report["sample_counts"],
        "skops_untrusted_types": untrusted,
        "dependencies": {name: version(name) for name in
                         ("mlflow", "scikit-learn", "skops", "numpy", "pandas", "kserve")},
        "source_hashes": {name: sha256(Path(name)) for name in
                          ("uv.lock", "dvc.lock", "scripts/train_historical_model.py",
                           "scripts/generate_training_fixture.py", "src/cogniflow_data/training.py",
                           "src/preprocessing_api/features.py")},
        "checks": ["local registry identity", "artifact tree", "skops allowlist", "input digests",
                   "deterministic dataset regeneration", "fresh-fit validation metrics",
                   "registered skops validation/test parity", "six-feature three-class inference",
                   "missing/corrupt artifact rejection", "reload recovery",
                   "unapproved packaging rejection"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.root, args.model_name, args.version, args.run_id, args.artifact_sha256)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(result["status"])


if __name__ == "__main__":
    main()
