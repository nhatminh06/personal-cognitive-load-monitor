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

Dummy majority, logistic regression, and random forest each receive an MLflow run with model type, supported hyperparameters, dataset checksum, Git revision, feature schema, label provenance, cutoff, and validation metrics. Selection uses validation macro F1 only. Only the selected model is evaluated on the held-out test set and registered with `approval_status=candidate`. The report distinguishes the standalone export's `exported_joblib_sha256` from `registered_artifact_sha256`, a deterministic digest over every relative filename and byte in the artifact tree referenced by the registered model version.

## Explicit approval boundary

Training never approves, promotes, serves, or deploys a model. Owner approval is a separate command requiring the exact candidate version and digest:

```fish
uv run python scripts/approve_model_candidate.py \
  --tracking-uri sqlite:///mlflow-phase2.db \
  --model-name cognitive-load-classifier-phase2 \
  --version VERSION --expected-digest SHA256 --actor nhatminh06 --approve
```

Before recording approval tags, the command downloads the artifact referenced by that exact model version and requires its computed tree digest to match both the candidate tag and `--expected-digest`. This does not assign a production alias or deploy anything.

## Security

- Trino exposes only version-pinned snapshot operations; requests and pagination must remain `http://127.0.0.1:8081`, and redirects are rejected.
- Local joblib loading retains the production SHA-256 gate. Only locally generated artifacts are trusted.
- No secrets are stored in manifests, MLflow metadata, reports, or DVC.
- SEC-022 is unchanged. Spark, Kubernetes serving, Kubeflow, KServe, Knative, Argo CD, Terraform cloud apply, and remote deployment are outside this phase.

## Local verification evidence

Verified on October 26, 2026:

- Full regression: 119 passed; combined coverage 88.95% (81% gate).
- Ruff: passed. MyPy: passed for 17 source files.
- DVC: all stages reproduced or skipped as unchanged; a second status check reported the pipeline up to date.
- Dataset: `cogniflow-module3-training-synthetic-v1`, 180 rows (60 per proxy class), SHA-256 `6679e9edb87451ee968e21c0aef5280226b2cf609554e048ec365378c3aca80f`.
- Split: 108 train, 36 validation, 36 held-out test, in chronological order.
- MLflow runs: dummy `22a7265361184beda2ba9887c8bf4c77`, logistic `e12a3178ebd146e6b64dd44ca1addeb6`, random forest `94253b877a8c4d45a36abba85a25d4bc`.
- Registered candidate: model version 2, registered artifact-tree SHA-256 `13137be7ce4c885877d7968afa0177be31cff60a4b2e33707893a7698c3b62ae`; independently downloaded and verified against the model version's `models:/m-c1dfec4cea3e4e1b8f71df1365fcfdec` source.
- Standalone exported joblib SHA-256: `e3a3449a1e6b2a4ac301d3111c6d21ab5f78e626edd63b70113332de080bbafb`. It is not used as the registered-artifact approval digest.
- Validation accuracy/macro F1: dummy 0.3333/0.1667; logistic 1.0/1.0; random forest 1.0/1.0. Selected random-forest held-out accuracy/macro F1: 1.0/1.0.

The perfect selected-model result reflects a deliberately separable synthetic integration fixture. It is pipeline evidence only and is not evidence of real-world or medical cognitive-load accuracy.

## Next phase

Phase 3 may consume an explicitly approved immutable model version for local serving-contract verification. It must retain digest verification and must not infer production approval from candidate registration alone.
