# Module III Phase 2: reproducible ML training

## Architecture and boundaries

```text
HistoricalFeatureRow JSONL + verified feature manifest
SyntheticLabel JSONL + training/label cutoff
                 -> validated decision_id join
                 -> chronological 60/20/20 dataset
                 -> dummy / logistic / random-forest comparison
                 -> held-out test evaluation
                 -> MLflow candidate registration
                 -> separate explicit approval (never deployment)
```

The bounded integration fixture contains 180 chronological examples with 60 examples per synthetic class. Feature observations and labels are emitted by separate generator paths from a deterministic latent scenario; labels are never copied from feature rows. These metrics measure reproducibility against `synthetic_proxy` labels, not clinical or real-world cognitive-load accuracy.

The preserved real Delta snapshot has only one row and no adequate authoritative label source. It is therefore not used to claim real-data training. Real Delta-backed training remains blocked until a retained, version-pinned snapshot and separately available labels meet the same contract.

## Reproducibility and lineage

The DVC pipeline records input SHA-256 values, output dataset identity and checksum, exact feature order/schema, actual transformation commit, UTC training cutoff, label provenance, sample counts, validation status, and chronological split indices. Synthetic input explicitly has no Delta version.

```fish
uv run dvc repro phase2_train
uv run dvc status
cat data/processed/module3/training_manifest.json
cat reports/module3/phase2-metrics.json
```

Generated JSONL, manifests, model files, MLflow databases/artifacts, and reports remain outside Git.

## Local MLflow

The verified workflow uses a local SQLite backend and local artifact storage; it does not bind a public server or use cloud credentials. MLflow failures propagate and fail the training command.

```fish
set tracking_uri sqlite:///mlflow-phase2.db
env PYTHONPATH=src uv run python scripts/train_historical_model.py \
  --dataset data/processed/module3/training_dataset.jsonl \
  --manifest data/processed/module3/training_manifest.json \
  --output models/cognitive_load_phase2.joblib \
  --report reports/module3/phase2-metrics.json \
  --tracking-uri $tracking_uri

uv run mlflow ui --host 127.0.0.1 --port 5000 --backend-store-uri $tracking_uri
```

Dummy majority, logistic regression, and random forest each receive an MLflow run with model type, supported hyperparameters, dataset checksum, Git revision, feature schema, label provenance, cutoff, and validation metrics. Selection uses validation macro F1 only. Only the selected model is evaluated on the held-out test set and registered with `approval_status=candidate` plus its SHA-256.

## Explicit approval boundary

Training never approves, promotes, serves, or deploys a model. Owner approval is a separate command requiring the exact candidate version and digest:

```fish
uv run python scripts/approve_model_candidate.py \
  --tracking-uri sqlite:///mlflow-phase2.db \
  --model-name cognitive-load-classifier-phase2 \
  --version VERSION --expected-digest SHA256 --actor nhatminh06 --approve
```

This records approval tags only; it does not assign a production alias or deploy anything.

## Security

- Trino exposes only version-pinned snapshot operations; pagination must remain `http://127.0.0.1:8081`.
- Local joblib loading retains the production SHA-256 gate. Only locally generated artifacts are trusted.
- No secrets are stored in manifests, MLflow metadata, reports, or DVC.
- SEC-022 is unchanged. Spark, Kubernetes serving, Kubeflow, KServe, Knative, Argo CD, Terraform cloud apply, and remote deployment are outside this phase.

## Local verification evidence

Verified on October 26, 2026:

- Full regression: 101 passed; combined coverage 89.85% (81% gate).
- Ruff: passed. MyPy: passed for 17 source files.
- DVC: all stages reproduced or skipped as unchanged; a second status check reported the pipeline up to date.
- Dataset: `cogniflow-module3-training-synthetic-v1`, 180 rows (60 per proxy class), SHA-256 `44745685d680320537de7bca8169d4151598e7202888946d53cb52f8a546e67a`.
- Split: 108 train, 36 validation, 36 held-out test, in chronological order.
- MLflow runs: dummy `ad6323f27016427c9ffa0c0a0e0a2846`, logistic `fc4ff0fdb1a040278990fb34183baf73`, random forest `c980faa63ec648f091508e02a2577896`.
- Registered candidate: model version 1, artifact SHA-256 `e3a3449a1e6b2a4ac301d3111c6d21ab5f78e626edd63b70113332de080bbafb`.
- Validation accuracy/macro F1: dummy 0.3333/0.1667; logistic 1.0/1.0; random forest 1.0/1.0. Selected random-forest held-out accuracy/macro F1: 1.0/1.0.

The perfect selected-model result reflects a deliberately separable synthetic integration fixture. It is pipeline evidence only and is not evidence of real-world or medical cognitive-load accuracy.

## Next phase

Phase 3 may consume an explicitly approved immutable model version for local serving-contract verification. It must retain digest verification and must not infer production approval from candidate registration alone.
