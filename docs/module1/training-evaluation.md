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
uv run dvc repro --dry train_model drift_report
```

`reports/metrics.json` records dataset, split, pipeline-definition, parameter,
Git, feature-schema, dependency, membership, candidate-parameter, validation,
selection, audit-status, and exported-artifact identities. A clean second DVC
run proves unchanged declared outputs; MLflow run IDs and timestamps are not DVC
outputs. If local DVC objects are unavailable, restore them from the configured
local remote or regenerate only through declared stages—never copy unverified
outputs from another worktree.
