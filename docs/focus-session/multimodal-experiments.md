# Behavioral and multimodal effort experiments

PR 5 adds a local, candidate-only experiment path for predicting the user-provided
`self_reported_effort` rating (1–7). It does not change the six-feature Module I
API, Module III KServe serving, or any deployed model.

## Data source and snapshot

The authoritative local join is the focus-session SQLite store. PR 4 persists CV
window aggregates there; it does not publish CV records to Kafka, Bronze, or
Silver. A real export therefore requires all of the following:

- an explicit snapshot cutoff;
- `--authorize-private-data`;
- the owner's API key in `COGNIFLOW_EXPERIMENT_API_KEY` (never a command-line
  argument); and
- local output paths that remain outside version control.

The repository reads one owner-scoped SQLite transaction, excludes cancelled
sessions, and bounds windows and events by the snapshot cutoff. The builder then
validates the versioned event contracts, resolves append-only label corrections,
and joins exact session ID, window ID, UTC boundaries, and five-minute duration.
It preserves microseconds and requires `feature_cutoff == window_end`.

Dataset rows contain pseudonymous session/subject keys, aggregate behavioral and
CV values, source event IDs, cutoffs, and the target. Strict schemas reject extra
fields, so raw images, landmarks, embeddings, titles, source text, filenames,
URLs, credentials, and other private content cannot enter the export. Missing CV
is represented by null CV values plus `cv_available=0`; zero measurements are
never fabricated.

## Splits and experiments

Splits are deterministic and chronological. Whole subjects are assigned when at
least three subjects exist; otherwise whole sessions are assigned. Two-subject
datasets fail closed because three subject-disjoint splits are impossible. A
valid split needs at least 90 labeled windows, three indivisible groups, all
effort bands in train and validation, at least five test rows per band, and both
present and missing CV in training. One-subject results are explicitly marked
`within_subject` and do not support population-generalization claims.

The CPU-only scikit-learn experiments are:

- A: behavioral aggregates;
- B: CV aggregates on CV-present windows only; and
- C: behavioral plus CV aggregates and `cv_available`, using train-fitted median
  imputation.

Dummy-median, ridge, and bounded random-forest regressors are selected using
validation MAE only. Test data never selects a model. Predictions are clipped to
1–7 and projected to the reviewed LOW/MEDIUM/HIGH half-step bands. A, B, and C
are also evaluated on the exact same CV-present test windows. A separate full
cohort comparison covers A and missing-CV-aware C. C is preferred only when its
validation MAE improves by at least 0.25 and macro F1 is no more than 0.02 below
A; otherwise A remains preferred.

MLflow uses a local SQLite backend and records each artifact as an experimental
candidate. The default does not register, approve, alias, package, promote, or
serve a model. Synthetic engineering candidates cannot be registered.

## Current evidence and limits

Only engineering validation has run. The deterministic synthetic fixture has 90
windows across nine sessions, 72 CV-present windows, and 18 missing-CV windows.
It validates joins, lineage, missingness, splitting, training, and local MLflow;
its synthetic effort ratings are not user reports and its metrics are not
evidence of predictive validity. No authorized local dataset with enough genuine
labels was available, so empirical evaluation is `INSUFFICIENT_DATA`.

The manifest records schema and target versions, event digests, source snapshot
digest, cutoffs, counts, CV coverage, distributions, grouping and split policy,
seed, Git revision, and dataset/split SHA-256 digests. DVC adds three independent
stages after the existing pipeline and does not alter legacy stages.

Reproduce the synthetic engineering check locally:

```fish
uv run --extra dev dvc repro multimodal_experiments
uv run --extra dev pytest src/tests/test_multimodal_experiments.py
```

An authorized real export is intentionally separate:

```fish
set -x COGNIFLOW_EXPERIMENT_API_KEY (read -s -P 'API key: ')
env PYTHONPATH=src uv run python scripts/build_multimodal_dataset.py \
  --database data/focus-sessions.sqlite3 \
  --snapshot-cutoff 2026-01-31T00:00:00+00:00 \
  --authorize-private-data \
  --dataset /tmp/cogniflow-real/dataset.jsonl \
  --manifest /tmp/cogniflow-real/manifest.json \
  --splits /tmp/cogniflow-real/splits.json
set -e COGNIFLOW_EXPERIMENT_API_KEY
```

Do not commit or upload the real dataset, manifest, splits, MLflow database, or
model artifacts.
