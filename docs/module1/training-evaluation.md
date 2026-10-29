# Module I training and evaluation

The selection rules, evidence boundaries, results, and remaining blockers are
maintained in [`model-selection-policy.md`](model-selection-policy.md). This file
contains only the implementation reproduction procedure.

## Reproduce

The DVC stage records split configuration in `params.yaml`, writes train,
validation, and previously-observed CSVs, and tracks candidates in the isolated
`cogniflow-module1-engineering-candidates` MLflow experiment. It never registers,
approves, packages, or promotes a model.

```fish
uv sync --frozen --all-extras
uv run dvc repro generate_data train_model drift_report
uv run dvc repro package_engineering_model
uv run dvc repro --dry train_model drift_report
```

`reports/metrics.json` records dataset, split, pipeline-definition, parameter,
Git, feature-schema, dependency, membership, candidate-parameter, validation,
selection, audit-status, and exported-artifact identities. A clean second DVC
run proves unchanged declared outputs; MLflow run IDs and timestamps are not DVC
outputs. If local DVC objects are unavailable, restore them from the configured
local remote or regenerate only through declared stages—never copy unverified
outputs from another worktree.

## Local serving parity

The engineering package is explicitly synthetic and unapproved. The production
packager and approved-only runtime path remain unchanged.

```fish
set package build/module1-engineering-package
set manifest $package/model-package.json
set -lx APP_ENV development
set -lx MODEL_PATH $package/cognitive_load_model.skops
set -lx MODEL_PACKAGE_PATH $manifest
set -lx MODEL_NAME cognitive-load-engineering
set -lx MODEL_VERSION engineering-2b
set -lx MODEL_ARTIFACT_SHA256 (jq -r .source_model_sha256 $manifest)
set -lx MODEL_SHA256 (jq -r .packaged_model_sha256 $manifest)
set -lx MODEL_DATASET_SHA256 (jq -r .dataset_sha256 $manifest)
set -lx MODEL_FEATURE_SCHEMA_VERSION 1.0
uv run --extra kserve python scripts/serve_engineering_model.py \
  --model_name $MODEL_NAME --http_port 8080 --allow-synthetic-engineering
```

Run `uv run pytest -q src/tests/test_module1_serving_http.py` for bounded real
loopback KServe-to-FastAPI parity, malformed-input, and unavailable-backend
checks. Missing, corrupt, digest-mismatched, schema-incompatible, or unexpected
serialized types fail before readiness. Skops archives are not byte-stable, so
the package records and verifies each produced digest; prediction parity is exact.
