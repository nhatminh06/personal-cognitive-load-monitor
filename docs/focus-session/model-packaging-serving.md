# Strict focus-model packaging and local serving

PR 6 adds a separate local runtime for the `self_reported_effort` experiment
target. It does not change the legacy six-feature `POST /predict` contract or
the Module I Knative and Module III KServe Standard runtimes.

## Package contract

A package directory contains exactly:

- `model.skops`: the train-fitted scikit-learn pipeline emitted directly by the
  trusted PR 5 experiment process; and
- `model-package.json`: canonical, compact, sorted JSON validated by the strict
  `FocusModelManifest` v1 contract.

The manifest binds the ordered feature contract, target, CV missingness policy,
preprocessing policy, estimator configuration, dataset and split digests, Git
revision, DVC stage/parameters, MLflow run, runtime versions, reviewed skops
types, source-joblib lineage digest, model digest, package digest, provenance
classification and approval state. The package digest covers the model bytes
and canonical manifest content excluding the digest itself.

Integrity is not approval. The allowed governance pairs are:

| Provenance | Approval status | Serving rule |
|---|---|---|
| `synthetic_fixture` | `TEST_FIXTURE_ONLY` | Explicit local test mode only |
| `experimental_candidate` | `candidate` | Rejected by serving |
| `approved_candidate` | `approved` | Rejected until a trusted verifier exists |

SHA-256 verifies package integrity; it does not authenticate approval. The
repository has no trusted focus-model approval authority, so manifest-provided
approval records are not authorization and every non-synthetic package fails
closed. A future genuine-model approval path requires a separately reviewed
trust mechanism. PR 6 creates no approval record and performs no registration
or promotion. Production focus-model inference remains blocked.

## Serialization boundary

The generic packager accepts only the `.skops` output recorded by the PR 5
report. It never accepts or loads a joblib/pickle path. Before deserialization,
the runtime validates the exact two-file layout, regular-file status, archive
size/member/path limits, metadata schema, model and package SHA-256 digests,
runtime compatibility and the exact skops unknown-type list. Only reviewed
`numpy.dtype` and `sklearn.tree._tree.Tree` types are allowed. It then checks the
loaded pipeline's exact feature order, step names/types, median imputer and a
finite one-row prediction.

Generated packages and model binaries remain ignored/DVC-managed and must not be
committed.

## Local API

`POST /v1/focus/predict` is authenticated with the existing `X-API-Key` owner
identity. The request supplies only a strict completed-window reference:

- session/window identifiers;
- exact five-minute UTC boundaries and feature cutoff;
- behavioral/CV contract versions and explicit CV availability; and
- an empty label-lineage field.

The server retrieves the owner-scoped behavioral/CV aggregate events from
SQLite. It does not trust client-supplied feature vectors, labels, private text,
URLs, filenames, frames, landmarks or embeddings. Unknown fields are rejected.
The package constructs the canonical pandas feature order and reuses its fitted
preprocessing. Missing CV remains null with `cv_available=0`; CV-only packages
reject missing CV. There is no fallback to the legacy model.

The response includes the bounded 1–7 rating, reviewed half-step band, package
identity/digest, schema versions, cutoff, CV availability, provenance and an
explicit fixture flag. It contains no probability or confidence field.

Additive probes are available at `/v1/focus/health` and `/v1/focus/ready`.
Invalid, absent, unapproved or unauthorized packages fail readiness/inference
closed without changing legacy readiness.

## Local synthetic reproduction

```fish
uv run --extra dev dvc repro focus_fixture_package

env PYTHONPATH=src uv run python scripts/verify_focus_package.py \
  models/focus-fixture

set -x APP_ENV development
set -x FOCUS_MODEL_TEST_MODE true
set -x FOCUS_MODEL_PACKAGE_PATH models/focus-fixture
set -x COGNIFLOW_API_KEY (read -s -P 'Local API key: ')
uv run uvicorn preprocessing_api.main:app --host 127.0.0.1 --port 8000
```

Submit a request only after creating an authenticated focus session and storing
its completed behavioral/CV aggregate window. Stop the server with `Ctrl+C`,
then remove local generated outputs explicitly when desired:

```fish
rm -r models/focus-fixture  # generated local fixture only
set -e APP_ENV FOCUS_MODEL_TEST_MODE FOCUS_MODEL_PACKAGE_PATH COGNIFLOW_API_KEY
```

Do not use fixture mode for genuine data or production. Synthetic parity proves
package and serving correctness only, not predictive usefulness.
