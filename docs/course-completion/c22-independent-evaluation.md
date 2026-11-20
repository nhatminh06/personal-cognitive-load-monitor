# C2.2 — independent synthetic groups and KFP lineage

2026-11-17, America/Chicago. Starting main:
`a7a1d1b20c68df7bb04bd534299dab68a45cb9c9` (clean).
Implementation/training commit: `9bc1e97d49bfbda8289a59fa7614867db33e1d17`.
The final evidence commit contains this record and the [candidate packet](c22-candidate.json).
No branch, repository, worktree, cluster, cloud operation, image publication,
approval, deployment or push occurred. M10.3 NO-GO and SEC-022 remain unchanged.

## Prior candidate audit

The existing `cogniflow-fresh-synthetic-20261117/1` was independently checked
before implementation using its committed qualification command. Output matched
its [original packet](synthetic-candidate-20261117.json). Verified:

- Dataset `9ff25b2b325579c7142202436e870886eb0c76a110e0e36e3bb50fc197621a48`.
- Six ordered features/schema 1.0, registered signature, source/run and input hashes.
- Skops `138aba7d5a636ed69f296889eb037b8a5b2257b65964cd0ff665b4ff47933d61`.
- Registered tree `4119d9aa3cbe3ba63d69b434c11b0209eba8b1ff331603b5cb5459d23b423f60`.
- Run `84c010c6beea458d92727fb320399050`, chronological ranges 0:126/126:168/168:210.
- Old selection: validation macro-F1 then model name; random forest won a tie.
- All 42 validation and 42 test vectors overlap training. Those old results remain
  engineering-only evidence and were not replaced or relabeled.

Before new training, all files in the prior candidate directory were hashed;
comparison after new training/verification confirmed identical names and bytes,
including its registry database. No existing candidate tags or artifacts changed.

## Predeclared independent evaluation

The [protocol](c22-evaluation-protocol.md) was written before evaluation and
committed with the tested implementation before training. `feature_groups_v1`
groups the canonical six-feature vector, computed by the shared `feature_vector`.
Numeric values become floats, signed zero becomes 0.0; compact JSON bytes are
SHA-256 hashed. Labels, IDs and timestamps are excluded. Conflicting labels in
one group fail closed. Recomputed ratios avoid differing decimal encodings
separating equivalent raw inputs.

Within each class, group keys are ordered by SHA-256(`42:` + key). Allocate
floor(60%) groups to training, the next through floor(80%) to validation, and the
remainder to test. At least three groups per class are required. All rows of a
group stay together. The split records explicit zero-based indices plus SHA-256
binding protocol, dataset digest and membership. It is a group holdout, **not a
temporal forecast**; time/availability validation still applies to each row.

There are 60 unique groups (20/class), sufficient for 36/12/12 held-out group
allocation without modifying the generator. Actual rows differ from 60/20/20
because repeated groups have different sizes:

| Partition | Rows | Groups | LOW | MEDIUM | HIGH |
|---|---:|---:|---:|---:|---:|
| Train | 125 | 36 | 41 | 41 | 43 |
| Validation | 43 | 12 | 14 | 15 | 14 |
| Final test | 42 | 12 | 15 | 14 | 13 |

Pairwise group overlap: **zero** (train/validation, train/test, validation/test).
Assertions verify exhaustive disjoint indices, class representation, deterministic
assignment even after input order reversal, and rejection of overlapping membership
even if its hash is recomputed. This eliminates exact-vector leakage, not shared
synthetic latent rules. There are only 12 distinct test groups; repeated rows are
not independent scientific observations. Generalization to people, calibration,
fairness and psychological validity remain unestablished. A scientifically meaningful
next study would require authorized independent labels/populations, not further
synthetic accuracy optimization.

## Selection and measured results

Shared local/Module I/KFP policy: maximize **validation macro-F1**, then validation
accuracy, then exact ties prefer **majority → logistic regression → random forest**.
No tolerance, tuning budget or post-test model switch is used. Scaling is fitted
only on training. Forest uses 200 balanced trees/seed 42; logistic uses max_iter
1000/seed 42. Test metrics are computed only for the selected winner after selection.
The verification script subsequently checks that winner's test predictions without
using them to select another model.

| Candidate | Validation accuracy | Validation macro-F1 |
|---|---:|---:|
| Majority | 0.32558139534883723 | 0.16374269005847952 |
| Logistic regression | 1.0 | 1.0 |
| Random forest | 1.0 | 1.0 |

**Selected: logistic regression**, by the predeclared simpler-model exact tie rule.
Winner test accuracy/macro-F1: **1.0 / 1.0**. Test confusion matrix in LOW/MEDIUM/HIGH
order: `[[15,0,0],[0,14,0],[0,0,13]]`. These are newly measured synthetic results,
not reproduction of the historical 0.90/0.65 evaluation (still NOT_REPRODUCED).

## New immutable identities

New isolated local directory: `data/processed/c22-candidate-20261117/` (ignored,
retained on disk). Its SQLite registry and artifacts are separate from the old
candidate. Git contains review evidence and commands, not the binaries/database.
The unchanged deterministic generator yields the same dataset bytes as C2.1;
the new independent membership is distinguished by the split digest.

| Identity | Exact value |
|---|---|
| Dataset family | `cogniflow-module3-training-synthetic-v1`, schema 1.0 |
| Dataset SHA-256 | `9ff25b2b325579c7142202436e870886eb0c76a110e0e36e3bb50fc197621a48` |
| Split SHA-256 | `6a43e788f297a1c17e3ece4d57e587c103d093381308b1f282b63b38ce0edc2c` |
| Model name/version | `cogniflow-c22-independent-20261117/1` |
| Experiment | `cogniflow-c22-independent-20261117` |
| MLflow selected run | `cfe2e543f44043138e5b236e5f2115b5` |
| Logged model | `models:/m-6f61e759616f41e697fa7cc9f912a053` |
| Skops SHA-256 | `0861a20d77f9229d832a0145ebb28e56dae3b650a78eec2229e56dfa1a3a1c19` |
| Artifact-tree SHA-256 | `ed5be0c48c11a0d5315d43cc768df493e3839e09b07f3deaf7c9bddab6138197` |
| Auxiliary joblib SHA-256 | `08169996f0f9f9817c73bc1aa6e9ab46a6156ccf86249209df0f9ad39afaa2d9` |
| Training revision | `9bc1e97d49bfbda8289a59fa7614867db33e1d17` |
| Approval | `candidate`; not approved |

The packet records exact input, partition, evaluation, source and dependency digests,
class distributions and feature names. The run logs the dataset manifest, evaluation
and split hash; version tags bind split, dataset, source and feature schema.
No KFP IDs or component image values were added to this local run.

Training invocation: generate 210 rows with `scripts/generate_training_fixture.py`;
prepare with `--split-protocol feature_groups_v1`, cutoff
`2026-01-15T00:00:00+00:00` and the training revision above. Create the isolated
experiment with file artifact location under that directory, then run
`scripts/train_historical_model.py` against its dataset/manifest using the model
and experiment names above. Use `UV_CACHE_DIR=/tmp/cogniflow-fresh-uv` and explicitly
point tracking/registry URI to `sqlite:///` + absolute directory + `/mlflow.db`.
Use a new directory and model identity for any retraining; never overwrite these.

Safe independent re-verification of the retained candidate:

```bash
PYTHONPATH=src:. MLFLOW_DISABLE_AGENT_HINT=1 ./.venv/bin/python \
  scripts/qualify_local_candidate.py \
  --root data/processed/c22-candidate-20261117 \
  --model-name cogniflow-c22-independent-20261117 --version 1 \
  --run-id cfe2e543f44043138e5b236e5f2115b5 \
  --artifact-sha256 ed5be0c48c11a0d5315d43cc768df493e3839e09b07f3deaf7c9bddab6138197 \
  --output /tmp/cogniflow-c22-review.json
```

Observed `PASS_LOCAL_CANDIDATE_ONLY`: regenerated identical inputs/membership,
refitted validation metrics, independently verified registered tree and skops,
loaded through the actual offline predictor, checked all three classes, rejected
missing/corrupt bytes, recovered on reload, and confirmed production packaging
rejects the unapproved candidate. Candidate-only validator injection is confined
to this offline self-check; it is not a deployable approved manifest.

## KFP source and provenance status

The graph retains **six container components plus three importers**. One exact
component image digest is embedded in all six executors; code revision is checked
against the image's `COGNIFLOW_CODE_REVISION`. Caching stays disabled. Preparation
now emits independent groups; training rejects legacy chronological manifests.
The runtime job UUID placeholder supplies the run identity, not a caller-invented
constant in the compiled graph.

Training validation binds dataset, split, models checksum and selection policy.
Evaluation checks those bindings before loading; registration checks dataset,
split, selected model, policy and model bytes. Registry run/version tags now carry
split identity. Final provenance checks evaluation digest and registration identity
and records dataset, schema/names, split, code, component image, KFP run, MLflow run,
version, skops digest and artifact-tree digest. Approval additionally requires the
same independent split digest in run/version/manifest and rejects substitution.
Legacy candidates without this evidence cannot satisfy the new approval gate.

Compilation with a clearly test-only `localhost/cogniflow-kfp@sha256:aaaa…aaaa`
passed. The compiled image is a placeholder for **compilation only**, not a built,
scanned or qualified image. Local sequential component tests use explicitly synthetic
run/image fixtures and are **not evidence of KFP execution**. Real KFP run ID,
component image identities and runtime provenance for this candidate are **absent**.
No cluster was inspected or modified.

## Runtime authorization boundary and procedure

Before any live KServe qualification: obtain authorization for an isolated KFP
runtime and image operations, resolve the exact supported platform/image security
gates, execute the revised graph, independently retrieve its artifacts, and review
that new KFP candidate. Do not attach a fabricated KFP ID to this local candidate.
Then separately obtain authenticated model approval, package/sign immutable images,
and perform the [KServe acceptance protocol](model-candidate-qualification.md).
M10.3 NO-GO and the missing signed approval/package/image binding remain blockers.

Prerequisites: an explicitly authorized isolated local KFP v2 endpoint and object
store, MLflow service with retained artifacts, reviewed namespace/service accounts,
resource budget (six sequential tasks request 250m/512Mi and limit 1 CPU/2Gi),
authorized registry/image digest and source revision. The historical setup in
[Module III](../module3.md) is reference evidence, not approval
to recreate its cluster or bypass its development security limitations.

Commands below are a **future authorized procedure**, not executed here:

```bash
# Build/publish only after separate authorization; capture the actual repository digest.
docker build --build-arg COGNIFLOW_CODE_REVISION=9bc1e97d49bfbda8289a59fa7614867db33e1d17 \
  -f Dockerfile.kfp -t "$AUTHORIZED_REGISTRY/cogniflow-kfp:c22" .
# Resolve and independently verify that authorized image's digest, code and scans.
./.venv/bin/python scripts/compile_kfp_pipeline.py \
  --component-image "$VERIFIED_COMPONENT_IMAGE" --output /tmp/c22-kfp.yaml
```

Upload only the three synthetic feature/label/feature-manifest inputs to immutable
object keys in the authorized store, verify their packet digests, and submit through
the authorized endpoint (environment values must be real, reviewed values):

```python
import os
from kfp import Client
run = Client(host=os.environ['AUTHORIZED_KFP_ENDPOINT']).create_run_from_pipeline_package(
    '/tmp/c22-kfp.yaml',
    arguments={
        'feature_uri': os.environ['FEATURE_URI'],
        'label_uri': os.environ['LABEL_URI'],
        'feature_manifest_uri': os.environ['FEATURE_MANIFEST_URI'],
        'git_revision': '9bc1e97d49bfbda8289a59fa7614867db33e1d17',
        'training_cutoff': '2026-01-15T00:00:00+00:00',
        'mlflow_tracking_uri': os.environ['AUTHORIZED_MLFLOW_URI'],
        'mlflow_experiment': 'cogniflow-c22-kfp',
        'mlflow_model_name': 'cogniflow-c22-kfp',
    })
print(run.run_id)  # Record the real returned ID; do not substitute the local MLflow ID.
```

Require all six component states to succeed, inspect pod imageIDs and code identity,
compare returned split digest/counts/metrics, independently download registered
skops and tree hashes, and retain sanitized execution records. Submit a separate
corrupted-input run: validation must fail and no training/registration task may
run. If no authorized cluster exists, stop and request runtime authorization; no
cluster creation command was run or authorized by C2.2.

## Fresh validation

- Full suite: **623 passed, 2 skipped, 5 warnings**, 69.46s; **87.20%** across all
  nine coverage packages, above 81%. Same full-suite command as the fresh-main
  record, with `COVERAGE_FILE=/tmp/cogniflow-c22.coverage`; permitted loopback tracing.
- Ruff: `./.venv/bin/ruff check src scripts` passed.
- Scoped MyPy with explicit package bases/ignored missing imports: no issues in
  27 API/data/eventing/anomaly source files.
- KFP compilation, contract and negative provenance tests passed in full suite.
- Approval, sanitized packaging, KServe loading/failure and recovery tests passed.
- Helm lint/default render passed; icon recommendation only.
- Changed-file Gitleaks 8.30.0 scan: no findings; private Track B evidence not read.
- Two skips are scanner fixtures using the default unavailable scanner path;
  the actual changed-file scan used the available explicit binary separately.
- Final focused result: **77 passed, 1 warning**, 9.68s. Git whitespace and evidence links checked.

**Decision:** eligible for owner review as an independent-group synthetic engineering
candidate, **not ready for model approval or KServe deployment**. Group holdout and
selection defects are addressed; genuine KFP execution and authenticated release
provenance/security acceptance remain outstanding.
