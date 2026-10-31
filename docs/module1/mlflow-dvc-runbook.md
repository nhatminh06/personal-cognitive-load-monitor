# MLflow and DVC runbook

Use a persistent local SQLite registry and filesystem artifacts:

```bash
uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlartifacts
MLFLOW_TRACKING_URI=http://127.0.0.1:5000 uv run dvc repro
uv run dvc repro  # expected: every stage unchanged
```

The repository DVC remote is local (`.dvc-storage`) and suitable for reproducible offline demonstrations. Do not commit `mlflow.db`, `mlartifacts`, `.dvc-storage`, or model binaries. Deployment must select an exact `models:/cognitive-load-classifier/<version>` URI; aliases, stages such as `latest`, and arbitrary pickle discovery are not accepted.

The immutable production chain is:

```text
DVC dataset digest -> training run -> MLflow registered numeric version
-> solo-owner educational authorization metadata -> artifact-tree SHA-256 verification
-> .skops-only package -> OCI repository digest -> deployment -> prediction provenance
```

The manual `production-release` workflow requires an exact owner acknowledgment
and binds authorization to the repository, owner identity, main revision, MLflow
name/version/run and artifact digest. `scripts/package_approved_model.py` checks
that solo-owner educational authorization plus the registered and downloaded
tree digests, `.skops` format, dataset/git/schema provenance and canonical six
features without deserializing the model. This is not independent review.

Serving rechecks the unsigned package manifest and model digest before loading;
that provides integrity after a trusted package is chosen, not independent
authorization. A future release must verify a signed exact model tuple and bind
it to the exact package and OCI digest. Missing or mismatched material fails
closed; production never selects `demo_rule` implicitly.

Versions carrying the earlier `synthetic_proxy_engineering_only` approval scope
are intentionally not packageable by this contract. Register a new candidate
version for an owner-authorized release; do not rewrite historical approval tags.

The existing candidate remains unchanged and unapproved. The bounded cloud
design stores registry metadata in persistent single-writer SQLite and artifacts
in GCS; its availability and backup limitations are documented separately.

The KFP training path consumes explicit feature, label and feature-manifest
artifacts rather than a DVC checkout. Its MLflow run records those input hashes
and the validated `dataset-manifest.json`; it must not invent a DVC revision.
Module I's separate DVC evidence comes from the reviewed release commit's
`dvc.yaml` and `dvc.lock` plus the existing reproducibility checks. Reviewers
must compare those inputs with the KFP hashes before claiming the same dataset.
