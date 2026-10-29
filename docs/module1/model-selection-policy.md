# Module I model candidate selection policy

This policy separates model-quality evidence from approval and release authority.
It does not approve a model. The local kind qualification evidence has an
independent reviewer decision of **PENDING** and does not qualify any registered
model or GKE target.

## Current evidence and decision

The local `cognitive-load-classifier` registry contains versions 1–11. MLflow
`READY` means an artifact was registered, not selected or approved. None has an
independently authenticated approval. Versions 8 and 10 are the only entries
with the recorded dataset hash, synthetic label provenance, six-feature
signature, evaluation artifact, and Git source tags; neither passes this policy.

`reports/metrics.json` compares candidates on the same 500-row synthetic
dataset, date-sorted 400/100 split, six ordered features, preprocessing path,
and metric functions:

| Candidate | Accuracy | Macro F1 | Interpretation |
|---|---:|---:|---|
| Rule-label identity check | 1.00 | 1.00 | `y_test` compared with itself; not a predictive baseline |
| Dummy majority | 0.60 | 0.25 | Minimum predictive baseline |
| Logistic regression | 0.96 | 0.9514687100893998 | Best recorded predictive candidate |
| Registered random forest | 0.88 | 0.8678356121965144 | Selected by code without a recorded selection rule |

The random forest is not justified by recorded performance. The logistic result
does not automatically justify selecting logistic regression: one test partition
is serving as model-selection evidence, there is no validation partition, and
labels are derived from the same rule represented by the features.

## Evidence gates

A candidate is eligible for comparison only when one immutable record contains:

1. dataset source, authorization, label definition and label provenance;
2. deterministic training configuration and locked dependency versions;
3. exact Git commit, DVC lock digest, dataset digest, and input hashes;
4. every random seed, including library and split seeds where applicable;
5. immutable train, validation, and held-out test membership and rationale;
6. duplicate, temporal, target-leakage, and person/session/group-overlap results;
7. feature-schema version, ordered names, types, nullability, and cutoff semantics;
8. identical splits, preprocessing, metrics, and tuning budget for fair baselines;
9. MLflow name/version/run/source plus tree, model, evaluation, package, and data digests;
10. minimal locked serving dependencies and six-feature schema 1.0 compatibility;
11. skops serialization, exact untrusted-types result, reviewed allowlist, and
    runtime vulnerability/license disposition;
12. intended/prohibited use, population, OOD, privacy, fairness, calibration,
    monitoring, rollback, and expiry limitations; and
13. an independent approval record authenticated by the release trust root.

Predeclare primary metric, thresholds, tie breakers, allowed model families,
and complexity/latency constraints before evaluation. Selection uses validation
evidence only. Evaluate the held-out test once after selection; switching after
seeing it requires a new experiment and test set. Prefer the simpler candidate
in a statistical tie unless an operational requirement justifies complexity.

## Three separate decisions

### Engineering validation

Answers whether training is reproducible, schema-compatible, safe to load, and
better than fair baselines on the stated dataset. Present synthetic results can
support only this scope. They do not establish that proxy labels or predictions
represent human cognitive load.

### Scientific validation

Requires authorized genuine labels, a measurement construct, leakage-safe
person/session grouping, external held-out population, calibration, appropriate
subgroup analysis, temporal/OOD evaluation, and independent methodology review.
It is **BLOCKED**. Runtime currently requires `label_provenance=synthetic_proxy`;
genuine-label serving needs a separately reviewed provenance-contract extension
while preserving the legacy feature and output contracts.

### Release authorization

Requires an independently authenticated decision for one exact candidate and
scope after required quality gates pass. Selection is not authorization. Kind
qualification, MLflow `READY`, mutable tags, packaging, or an image signature
alone is not authorization.

## Approval trust design

`approve_model_candidate.py` accepts a caller-provided actor and uses the same
MLflow authority to write mutable `approved` tags. The packager verifies tags
and artifact digest, but an authorized registry writer can forge the actor,
self-approve, or replace the tuple. Unsigned manifests and unkeyed hashes can be
recomputed. The release signs an OCI image but does not emit a signed predicate
binding that image to the approved model tuple.

Future approval must use this chain:

`distinct protected reviewer → signed approval predicate → verified package → signed model-to-OCI binding → attestation-gated deployment → runtime equality`

- Use a protected `model-approval` environment with required reviewers and
  prevent-self-review. Candidate author, reviewer, and release initiator must be
  distinct where the platform can enforce it.
- Restrict approval identity to the exact main-branch workflow through OIDC;
  only it may issue approval attestations. MLflow tags become hints only.
- Sign a canonical strict-schema DSSE/in-toto predicate covering repository,
  unique approval ID, model name/version/run/source, tree/model/data/DVC/Git/
  schema/evaluation/limitations digests, ordered features, label provenance,
  reviewed skops types, author/reviewer identities, issue/expiry, and scope.
- Packaging verifies issuer, exact workflow/ref, signature bundle, transparency
  evidence, expiry/revocation, scope, and every signed identity against freshly
  resolved registry/artifact facts before copying bytes.
- Release signs a second predicate whose subject is the exact OCI digest and
  binds approval, package, model, artifact, dataset, source, scan, SBOM, and
  provenance identities. Deployment derives values from this predicate.
- Keep append-only approval/revocation and publication records. Replay is valid
  only for the identical approval ID, package, OCI digest, and scope.
- Permit production publication only to protected release identity/IAM and an
  immutable repository. Deny the legacy ephemeral joblib/GHCR output at deploy.

This blocks forged tags and self-approval through authenticated reviewer
separation; substitutions through a signed exact tuple and re-resolution;
recomputed metadata through signed predicates; replay through scoped IDs and
expiry/revocation; and unauthorized publication through release-only IAM.

## Reproduction readiness

The locked legacy stages require the frozen Python environment, DVC, local
`storage` remote at `../../.dvc-storage`, and space for the 500-row CSV,
processed CSVs, model artifacts, SQLite/artifacts, metrics, and drift report.
A small scikit-learn random forest needs no GPU, cluster, network, or cloud.

Verify cache availability first. This isolated worktree lacks materialized
locked outputs, and not every output is available in its local cache. Do not
substitute dirty-worktree files without checking DVC hashes.

After cache availability is established, reproduce in a disposable copy with a
fresh MLflow store:

```fish
set -lx REQUIRE_MLFLOW true
set -lx MLFLOW_TRACKING_URI sqlite:///(pwd)/build/reproduction/mlflow.db
uv sync --frozen --all-extras
uv run dvc status
uv run dvc repro generate_data train_model drift_report
sha256sum data/raw/sample_data.csv data/processed/train.csv \
  data/processed/test.csv models/cognitive_load_model.joblib reports/metrics.json
uv run dvc repro generate_data train_model drift_report
uv run dvc status
```

Record dataset digest, exact membership, all candidate metrics, joblib and
registered skops tree/model digests, evaluation digest, Git/DVC/schema identity,
and minimal dependency lock. The second run must report no changed outputs.
Byte-identical models are required only if declared; otherwise require identical
predictions, metrics, membership, and documented serialization variance.

## Current blockers

- no validation split or predeclared selection rule;
- no group identity/overlap assertion; duplicate dates can cross the split;
- selected random forest underperforms the logistic baseline;
- versions 1–11 lack independently authenticated approval;
- DVC does not bind an MLflow version or registered skops digest;
- broad ambient dependency snapshots are not minimal serving locks;
- no genuine labels or scientific validation;
- mutable approval tags and caller-supplied actor are not a trust root;
- no signed approval-to-package-to-image binding; and
- kind review, GKE compatibility, and the production compatibility matrix
  remain blocked independently.
