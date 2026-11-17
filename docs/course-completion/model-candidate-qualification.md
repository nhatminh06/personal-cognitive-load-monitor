# Synthetic candidate qualification — 2026-11-17

## Decision and scope

Starting `main`: `be95946a8ca0049f7ddaafc8f084ce1fe26f4f62`; initial worktree
clean. This record and the [machine-readable packet](synthetic-candidate-20261117.json)
belong to the local commit containing them. No branch, worktree, cluster, promotion,
approval, deployment, image publication or push was performed. The older checkout
and private Track B evidence were not accessed.

| Evidence category | Result |
|---|---|
| Historical documented 500-row evaluation | Exact locked report recovered read-only from Git; its metrics are verified as recorded |
| Independently reproduced historical evaluation | **NOT_REPRODUCED**: exact dataset/partitions/model unavailable |
| Newly trained 210-row synthetic evaluation | Independently regenerated inputs, refitted validation baselines, and checked registered skops predictions |
| Candidate | `cogniflow-fresh-synthetic-20261117`, version `1`, local registry |
| Approval | **UNAPPROVED**; `approval_status=candidate` remains unchanged |
| Production packaging | Correctly rejected: `model version is not explicitly approved`; no package created |
| KServe | Offline predictor qualification passed; Kubernetes runtime **NOT_RUN** |

## Historical recovery

Inspected `dvc.yaml`, `dvc.lock`, the training/evaluation implementations,
[model card](../model-card.md), [selection policy](../module1/model-selection-policy.md),
registry/packaging code, local cache paths and known Git paths. `.dvc/cache`, the
configured `../../.dvc-storage`, the required materialized CSV/model files,
`pr14-candidate.mlflow.db`, `mlflow-phase2.db`, and the Module I evaluation database
are absent. Existing `mlruns` output from regression fixtures has no associated
historical registry identity and is not a recovered candidate. Git has no versions
of the required `data/raw/sample_data.csv` or `models/cognitive_load_model.joblib`.
No broad filesystem/private-evidence search or older-checkout copy was performed.

Git commit `6003162c580aee4d0cd7c47b8dc1dc200e9adb23` contains
`reports/metrics.json` with MD5 `c74c92d6cbe5250f1e526bbf82799771`, matching the
current DVC lock. Read-only hash verification used `git show` bytes; the old report
was not restored into the current pipeline outputs. It records:

| Historical validation model | Accuracy | Macro-F1 |
|---|---:|---:|
| Majority | 0.65 | 0.2626262626262626 |
| Logistic regression | 0.86 | 0.8036356678147722 |
| Random forest | 0.90 | 0.8800607287449393 |

Partitions: 300 train / 100 validation / 100 previously observed audit rows.
Recorded dataset SHA-256:
`ab67e62ee1c401d135bb6ba32b9baf48bbcbf83c0bbbdec64fde366c21fbf0e7`;
locked input MD5: `b8408136bd0208331d2533c17248972f`.
The report itself records `git_dirty=true` at
`f394f80f7e8209c28f195e64f1298b7ed058ee3a`. A recovered report is neither a
reproduced evaluation nor proof of a clean training revision. Recovery stopped
at this boundary; no newly generated data is claimed as its original input.

The separate historical PR14 180-row candidate is also not recovered. It must
not be confused with either the historical 500-row evaluation or this new run.

## Exact new candidate identity

All newly generated inputs, the database, model and evaluation remain under the
ignored local directory `data/processed/fresh-candidate-20261117/`. They are
synthetic fixtures, not person data. Keep that directory for review: the Git commit
contains the sanitized packet and reproduction commands, not the database/binary.
Deleting the directory loses these exact run identities. A fresh retraining creates
new MLflow IDs and may change serialization/metadata digests even when metrics agree.

| Identity | Value |
|---|---|
| Dataset family / schema | `cogniflow-module3-training-synthetic-v1` / `1.0` |
| New content version | `sha256:9ff25b2b325579c7142202436e870886eb0c76a110e0e36e3bb50fc197621a48` |
| Feature input SHA-256 | `0615c7a6c3106d414d4a0618b73599d11ee75275903f3af7188f49a54e136d04` |
| Label input SHA-256 | `8cdcc8cd32c23e141ed3d4953ea147f0481b44e12d5d6917daf12449587402d3` |
| Registry name / version | `cogniflow-fresh-synthetic-20261117` / `1` |
| Experiment | `cogniflow-fresh-synthetic-20261117` |
| Selected run | `84c010c6beea458d92727fb320399050` |
| Logged model source | `models:/m-8e5b9c796bc14301aeccb26a0dcb97c8` |
| Registered artifact-tree SHA-256 | `4119d9aa3cbe3ba63d69b434c11b0209eba8b1ff331603b5cb5459d23b423f60` |
| Exact `model.skops` SHA-256 | `138aba7d5a636ed69f296889eb037b8a5b2257b65964cd0ff665b4ff47933d61` |
| Auxiliary joblib SHA-256 | `3fc3e8fdeb3ec20608b4b8d3faee1db25cddf8a18950bef9cb5e01402d84cc8d` |
| Training source revision | `be95946a8ca0049f7ddaafc8f084ce1fe26f4f62` |

The local tracking URI is `sqlite:///` followed by the absolute path of
`data/processed/fresh-candidate-20261117/mlflow.db` (four slashes before `home`).
Artifacts use the same directory's `mlartifacts/`. No hosted registry was contacted.
The packet contains evaluation, source-code, lockfile and exact raw-JSONL partition
digests; its dataset digest is the content version, not a mutable alias.

Six ordered numeric, non-null, finite features:
`focus_minutes`, `distraction_minutes`, `tasks_due`, `hours_to_deadline`,
`focus_ratio`, `distraction_ratio`. First three must represent integers at serving;
ratios must match the shared derivation. Output is exactly LOW/MEDIUM/HIGH.
Cutoff: `2026-01-15T00:00:00+00:00`. Chronological half-open row ranges:
train `[0,126)`, validation `[126,168)`, test `[168,210)`, each class balanced.
The preparation validator checks timing, label availability, decision uniqueness,
feature order, source lineage and split class coverage.

## New metrics and limitations

| New 210-row model | Validation accuracy | Validation macro-F1 |
|---|---:|---:|
| Majority | 0.3333333333333333 | 0.16666666666666666 |
| Logistic regression | 1.0 | 1.0 |
| Selected random forest | 1.0 | 1.0 |

Selected forest test accuracy/macro-F1: **1.0 / 1.0**, 42 rows (14 per class).
Parameters are the existing `candidate_models()` defaults: forest 200 trees,
class-weight balanced, seed 42; logistic StandardScaler fitted only on training
plus LogisticRegression with seed 42/max_iter 1000; majority most-frequent.
No tuning or model switching occurred after viewing the test partition.

The unmodified Phase 2 pipeline breaks validation macro-F1 ties by model name,
so it chooses random forest over equally scoring logistic regression. This is
**not** the Module I policy's preference for the simpler tied candidate. Owner
review must resolve this before treating the forest as a justified release choice;
do not relabel the current run as policy-conformant selection.

Labels and features share a deliberately separable latent fixture construction.
All 42 validation and all 42 test feature vectors also occur in training;
the packet records these counts. Decision/session IDs are generated identities, not people.
These metrics establish engineering behavior only, not generalization, psychological
validity, fairness, calibration, or a blind real-world test. No real-person/OOD
validation was performed. Intended use remains an educational synthetic demonstration;
medical, employment, surveillance and other high-impact uses are prohibited.

## Reproduction and independent verification

Training used the unchanged documented Phase 2 scripts with 210 samples, a new
name, and an isolated local experiment. The following creates a **new** run; do
not overwrite the retained directory or claim new run IDs reproduce its identity.
The guarded example below uses a separate reproduction directory and name:

```bash
export CANDIDATE_DIR="$PWD/data/processed/candidate-reproduction-20261117"
test ! -e "$CANDIDATE_DIR" || exit 1
export PYTHONPATH=src:.
export UV_CACHE_DIR=/tmp/cogniflow-fresh-uv
export MLFLOW_DISABLE_AGENT_HINT=1
./.venv/bin/python scripts/generate_training_fixture.py \
  --features "$CANDIDATE_DIR/features.jsonl" --labels "$CANDIDATE_DIR/labels.jsonl" \
  --manifest "$CANDIDATE_DIR/features.manifest.json" --samples 210
./.venv/bin/python scripts/prepare_training_dataset.py \
  --features "$CANDIDATE_DIR/features.jsonl" --feature-manifest "$CANDIDATE_DIR/features.manifest.json" \
  --labels "$CANDIDATE_DIR/labels.jsonl" --output "$CANDIDATE_DIR/dataset.jsonl" \
  --output-manifest "$CANDIDATE_DIR/dataset.manifest.json" \
  --training-cutoff 2026-01-15T00:00:00+00:00 \
  --git-revision be95946a8ca0049f7ddaafc8f084ce1fe26f4f62
```

Create the separate local experiment, then train:

```bash
./.venv/bin/python - <<'PYTHON'
import os
from pathlib import Path
import mlflow
root = Path(os.environ["CANDIDATE_DIR"])
mlflow.set_tracking_uri("sqlite:///" + str(root / "mlflow.db"))
mlflow.set_registry_uri("sqlite:///" + str(root / "mlflow.db"))
mlflow.create_experiment("cogniflow-reproduction-20261117",
                         artifact_location=(root / "mlartifacts").as_uri())
PYTHON
export MLFLOW_REGISTRY_URI="sqlite:///$CANDIDATE_DIR/mlflow.db"
./.venv/bin/python scripts/train_historical_model.py \
  --dataset "$CANDIDATE_DIR/dataset.jsonl" --manifest "$CANDIDATE_DIR/dataset.manifest.json" \
  --output "$CANDIDATE_DIR/model.joblib" --report "$CANDIDATE_DIR/evaluation.json" \
  --tracking-uri "sqlite:///$CANDIDATE_DIR/mlflow.db" \
  --experiment cogniflow-reproduction-20261117 \
  --model-name cogniflow-reproduction-20261117
```

For the retained candidate, the next safe executable check is:

```bash
PYTHONPATH=src:. MLFLOW_DISABLE_AGENT_HINT=1 ./.venv/bin/python \
  scripts/qualify_local_candidate.py \
  --root data/processed/fresh-candidate-20261117 \
  --model-name cogniflow-fresh-synthetic-20261117 --version 1 \
  --run-id 84c010c6beea458d92727fb320399050 \
  --artifact-sha256 4119d9aa3cbe3ba63d69b434c11b0209eba8b1ff331603b5cb5459d23b423f60 \
  --output /tmp/cogniflow-candidate-review.json
```

Observed `PASS_LOCAL_CANDIDATE_ONLY`. This assert-based self-check refuses `python -O`.
It independently resolves the local registry, verifies the full registered tree,
run/dataset identity and input hashes, regenerates inputs in temporary storage,
refits validation baselines, and recomputes validation/test metrics from the
registered skops model. It confirms all three classes through the actual predictor,
then tests missing/corrupt bytes, cleared readiness and successful reload.
It injects a candidate-only validator into an offline predictor instance; no
production manifest is forged and no server is started. The production packager
is independently exercised and must reject the unapproved version.

`skops.io.get_untrusted_types` returned only `sklearn.tree._tree.Tree`, covered
by the existing explicit allowlist. Versions: Python 3.11.17, sklearn 1.9.1,
MLflow 3.17.2, skops 0.16.0, NumPy 2.4.6, pandas 2.3.3, KServe SDK 0.20.0.
MLflow's environment export initially encountered a read-only uv cache and fell
back to dependency inference; it also warned about unpinned pip in conda metadata.
The exact frozen `uv.lock` and installed versions are recorded, but this artifact's
inferred environment is not a qualified minimal serving dependency lock.

## Packaging compatibility fix and validation

The production packager intentionally strips `registered_source`, and the transfer
verifier requires that sanitized key set. The serving validator still required
that unused field, rejecting legitimate transferred packages. The smallest fix
removes that field from its required set. Exact model/version, run field, digests,
feature schema, label provenance and approval checks remain. No storage path is
added back to published manifests. The packaging regression now passes the actual
packager output through the serving validator as well as transfer verification.
This test uses an isolated mocked approval fixture; the real candidate was not approved.

- Focused training, approval, packaging, client and KServe suite: **136 passed**, 3 warnings.
- Full suite / nine-package coverage: **606 passed, 2 skipped, 5 warnings; 87.13%**, 65.13s; 81% gate passed.
- The two full-suite skips use the default unavailable scanner path; the explicit
  changed-file Gitleaks scan below was run separately. No extra Git repository was
  created for scanner test fixtures.
- Ruff `check src scripts`: passed.
- Existing scoped MyPy: no issues in 27 files. New qualifier checked separately
  with `--follow-imports=silent`; broad import-following additionally exposes three
  pre-existing typing errors in `generate_training_fixture.py` outside that scope.
- Helm lint and default render: passed, icon recommendation only; no runtime inference.
- Provenance self-check: passed, including independent new-input regeneration.
- Privacy/secret check: Gitleaks 8.30.0 scanned the six changed/new files: zero findings. Scanner binary SHA-256 `96c11d219ed6bfa9efe28d6d2a6bbafdeba474079a6451753d3b8514d735df60`; redacted JSON report `/tmp/cogniflow-candidate-secrets.json`. No private Track B paths were scanned.
- Git whitespace and documentation links: checked before commit.

## Owner-review prerequisites and exact runtime blocker

1. Review this exact identity tuple and the simpler-model tie, synthetic overlap,
   test limitations, trusted skops type, dependencies, intended use and expiry/rollback.
2. A local training run is not a KFP run. The existing approval command requires
   genuine `kfp_pipeline_name`, `kfp_run_id`, immutable component image, matching
   version/run provenance tags and a logged dataset manifest. This candidate does
   not satisfy that authorization contract. Do not invent KFP identifiers or invoke
   approval with placeholders; separately authorized real pipeline execution and
   renewed review are needed for that route.
3. Mutable registry tags are not independently authenticated approval. The signed
   approval/package/image trust design in the selection policy remains outstanding.
   Disabled release workflows must stay disabled; this task does not authorize revival.
4. M10.3 remains **NO-GO**, with the two recorded HIGH findings unresolved. No new
   vulnerability/license clearance, signed image, or compatible cluster is claimed.

The immediate KServe runtime blocker is **no approved, production-package-eligible
candidate and no authorized exact-image/cluster acceptance**. Component qualification
cannot lift any of those gates. Production package digest and OCI image digest are
therefore intentionally absent, not placeholders represented as immutable evidence.

## Local Kubernetes acceptance protocol — not executed

After separate owner authorization and security/platform gates pass, use the
reviewed existing local cluster; never create a cluster from this protocol.
Re-resolve the approved tuple: if a KFP run produces a new candidate, replace every
identity with its separately reviewed values. Do not deploy this unapproved version.

1. Package through `scripts/package_approved_model.py` with exact name/version/run
   and tree digest; run `scripts/verify_release_package.py` and record package SHA-256.
   Resolve separately authorized API and KServe images to repository digests, verify
   signatures/scans and embedded package bytes. Record cluster context, UID, platform
   versions, images and package in the acceptance transcript.
2. Render the existing Helm chart using a reviewed local acceptance values file:
   `kserve.enabled=true`, `kserve.deploymentMode=Standard`, `kserve.name` equal to the
   approved name, `config.inferenceMode=kserve`, exact model/version/schema and all
   three digests, both repository/image digests, and an existing API-key Secret.
   Use the same namespace consistently. Review the render before applying.
3. Only after authorization, install that reviewed render. Run
   `kubectl --context "$CONTEXT" -n "$NS" wait --for=condition=Ready \
   inferenceservice/"$MODEL_NAME" --timeout=180s` and save conditions plus actual pod
   `imageID` digests. Port-forward the resolved predictor service to loopback 18080
   and the API service to loopback 18000. Verify direct model readiness and metadata.
4. Build three canonical six-feature requests from one row of each validation class
   using `feature_vector`; POST to
   `http://127.0.0.1:18080/v1/models/$MODEL_NAME:predict` with
   `feature_names` and `instances`. Require LOW/MEDIUM/HIGH respectively, exact
   prediction counts and approved provenance. Do not send only four raw values to KServe.
5. POST each corresponding four-field input to `http://127.0.0.1:18000/predict` with
   `X-API-Key` supplied privately. Require matching classes and
   `inference_source=kserve`; missing/wrong credentials must return 401.
6. Corruption test: in a separately authorized isolated negative workload, supply a
   copy with one changed model byte while retaining the expected digest. It must
   fail loading and remain not Ready; repeat missing model and mismatched expected
   identity. Never alter the retained registry artifact. Record startup error and
   failed readiness, then remove only the negative workload.
7. For no-fallback acceptance, temporarily interrupt only the authorized predictor
   service path. API prediction must fail (mapped backend 5xx, never a demo-rule 200).
   Restore connectivity and confirm matching provenance and KServe inference again.
8. Delete one exact predictor pod in the acceptance namespace, observe a new pod UID,
   await `InferenceService` readiness again, and repeat all three direct/API requests.
   Record imageID/model/package identity before and after; no model substitution is allowed.

Retain sanitized request/status/provenance results, Ready conditions, pod UIDs,
immutable digest ledger, failure/recovery timing and teardown of only acceptance
resources. Never include API keys, local storage URLs or private evidence. Any
failed gate leaves runtime acceptance incomplete.

## C2.2 follow-up

The original candidate above is unchanged. See [C2.2 independent evaluation](c22-independent-evaluation.md)
for a separate candidate with disjoint feature groups, explicit simplicity tie-breaking,
and stronger KFP split lineage. It remains unapproved and has no real KFP runtime evidence.
