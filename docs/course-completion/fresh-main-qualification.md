# Fresh-main qualification — 2026-11-17

## Baseline and scope

Repository: `/home/pnmynh/Documents/personal-cognitive-load-monitor-fresh`.
Starting commit: `809d3a860e305533de77c7296fa510bca8c71da6`, branch `main`.
The worktree was clean before installation/edits. `git fetch origin main`
succeeded and `git rev-parse HEAD origin/main` returned that same commit twice.
No `AGENTS.md` was present. The authoritative [rubric](../course-rubric-2026.md),
[submission checklist](../submission_checklist.md), and [evidence index](evidence-index.md)
were read before changes. This report belongs to the local commit containing it;
validation below covers the starting source plus the changes described here.

No historical checkout was accessed. No branch, worktree, cluster, approval,
promotion, deployment, image publication, cloud access, benchmark, or push occurred.
Track B privacy boundaries, SEC-022, disabled release workflows, and the
[historical deployment-runner NO-GO](../evidence.md) remains unchanged.

## Reproducible checks

Python 3.11.17; dependencies installed into a new `.venv` with
`UV_CACHE_DIR=/tmp/cogniflow-fresh-uv uv sync --frozen --all-extras`.
The first sandbox attempt failed DNS resolution; the authorized network retry
succeeded without modifying the lockfile. Logs are local `/tmp/cogniflow-fresh-*`
files, not portable submission artifacts; the commands and results are recorded here.

| Check | Fresh result |
|---|---|
| Complete regression / nine-package coverage | **606 passed, 2 skipped, 5 warnings; 87.13% coverage**, 73.15s; 81% gate passed |
| KServe predictor and SDK adapter | 27 passed, 1.62s |
| API, events, anomaly, integrated flow, KServe, client, packaging | 206 passed, 1 warning, 3.59s |
| Module II compatibility selection | 72 passed, 0.43s |
| Ruff: `./.venv/bin/ruff check src scripts` | All checks passed |
| Existing scoped MyPy | No issues in 27 source files |
| KFP compilation | Passed; nine DAG tasks, compile-only placeholder image digest |
| Helm lint / default render | Passed; six documents; icon recommendation only |
| Kubernetes structural validation | NOT_RUN: no verified core OpenAPI/CRD schema bundle in the fresh checkout; validator regressions run in the suite |
| Terraform backend-free validation | NOT_RUN: `terraform -chdir=infra/terraform/gke validate -no-color` reports locked Google provider 5.45.2 absent from cache; no init/apply or credentials used |
| Secret scan | NOT_RUN: `gitleaks` unavailable; secret-report gate tests are not a secret scan |
| DVC status | Executed; missing cached outputs and source drift reported, not reproducible/current |
| Git whitespace | `git diff --check` passed |

The two skips are the exact-scanner checks in `test_release_secret_scan.py`
(`exact scanner unavailable in this test job`). The five warnings are collection,
Starlette/SQLAlchemy deprecation and MLflow integer-schema warnings.

Full-suite command (authorized loopback access allows the real tracing HTTP tests):

```bash
COVERAGE_FILE=/tmp/cogniflow-fresh.coverage ./.venv/bin/python -m pytest src/tests \
  --cov=src/preprocessing_api --cov=src/cogniflow_data \
  --cov=src/cogniflow_eventing --cov=src/cogniflow_anomaly \
  --cov=src/cogniflow_kserve --cov=src/cogniflow_contracts \
  --cov=src/cogniflow_sessions --cov=src/cogniflow_edge \
  --cov=src/cogniflow_focus --cov-report=term-missing --cov-fail-under=81
MYPYPATH=src ./.venv/bin/mypy --explicit-package-bases --ignore-missing-imports \
  src/preprocessing_api src/cogniflow_data src/cogniflow_eventing src/cogniflow_anomaly
./.venv/bin/python scripts/compile_kfp_pipeline.py \
  --component-image ghcr.io/cogniflow/training@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --output /tmp/cogniflow-fresh-kfp.yaml
helm lint helm/cognitive-load-monitor
helm template cognitive-load-monitor helm/cognitive-load-monitor \
  --namespace cognitive-load > /tmp/cogniflow-fresh-helm.yaml
./.venv/bin/dvc status
```

DVC initially failed because its temporary index under `/var/tmp/dvc/repo` was
read-only; an authorized retry succeeded. No data was generated or pulled.

## Model provenance and evaluation

**0.90 random forest versus 0.65 majority: documented, not reproduced.**
`data/raw`, `data/processed`, and `models` contain no required artifacts;
`reports/metrics.json` is also absent. The configured DVC remote
`../../.dvc-storage` does not exist. `dvc status` confirms missing cached outputs,
and also reports changed `src/cogniflow_data/training.py` for `phase2_dataset`.
Do not run the generator and describe the resulting evaluation as historical reproduction.

The exact DVC-recorded input MD5 is `b8408136bd0208331d2533c17248972f`.
Expected train/validation/audit MD5s are respectively
`032713681eb26a5532ad54d1fd34d31c`, `73ef967813119253ba3adbfc7bef18ac`,
and `61c19b94cb09a525994518e72177b58b`.
The recorded metrics MD5 is `c74c92d6cbe5250f1e526bbf82799771`;
model MD5 is `a7b46845606216830b42f2672ad18691`.
These are lockfile identities, not freshly verified file hashes.
`params.yaml` additionally pins the engineering source-model SHA-256
`1a65d25424963d185465183a8f589e30aa8a15b15218074c01e88c4bfab0d893`.

Source inspection confirms six ordered features: focus minutes, distraction
minutes, tasks due, hours to deadline, focus ratio, distraction ratio. Training
and serving share their implementation. `scripts/train_model.py` compares dummy,
logistic regression, and random forest on chronological timestamp-group
60/20/20 partitions, using train-only fitting. Selection is validation macro-F1,
then accuracy and declared complexity order. The last partition was previously
observed, so it is an audit set, not an independent blind test. This training
path logs isolated engineering candidates; it does not register or approve them.

The separate historical Phase 5 registry candidate is
`cognitive-load-classifier-pr14/1`, run `ad5c8cb2ae864ffe828da259719148bc`,
180 rows split 108/36/36, dataset SHA-256
`6679e9edb87451ee968e21c0aef5280226b2cf609554e048ec365378c3aca80f`,
artifact-tree SHA-256
`3c46d07c58f733119581b3fbb08fcd4c2080a7d74ac2ecddd1903f1514d1c20a`.
It is a different dataset/result from the 500-row model-card comparison.
Its registry/artifact are absent here; these identifiers remain historical,
not independently revalidated. No candidate was newly registered.

Training, candidate-registration, approval and packaging regressions validate
contract behavior with fixtures. Packaging checks exact version/run identity,
registered tree digest, dataset/schema metadata, skops layout, and authenticated
approval provenance before producing a serving manifest. These passing tests do
not establish approval or integrity of an unavailable historical artifact.

## KServe qualification and concrete fix

The predictor already verifies `.skops` bytes and provenance before loading,
checks six feature names and LOW/MEDIUM/HIGH classes, rejects nonfinite or
inconsistent derived features, and validates output classes/counts. The API
client checks provenance and fails closed on backend errors rather than
falling back to the rule model. Existing engineering tests serialize and load
real temporary skops fixtures; they do not use or approve a historical model.

A real gap was fixed in `CogniFlowModel.load`: clear adapter readiness before
attempting a reload. Previously, an exception after a successful load left the
adapter ready while the predictor had cleared its verified model. The new
regression loads, removes the artifact, verifies not-ready and rejection, restores
the artifact, and verifies successful recovery. Only the shared adapter and its
regression needed changes; its CLI callers, exports and configuration are unchanged.

This is source/component qualification, not Ready `InferenceService` evidence.
No Kubernetes API or live registered model was used.

## Integrated local demonstration

Run `./.venv/bin/python -m pytest -q src/tests/test_fresh_component_flow.py`.
Fresh result: **1 passed**. The test uses actual FastAPI authentication and
`demo_rule` inference; it captures the generated events at the publication
boundary and routes them through the real consumer and detector/store code.
It replaces network transport with in-process ASGI and an outbox HTTP adapter.

Observed assertions:

- Two authenticated requests succeed; two unauthenticated requests return 401.
- Four real API events pass schema validation and omit the API key and raw features.
- Consumer persists four events; duplicate delivery leaves four rows.
- Detector persists the same events and produces one `inference_error_ratio` alert.
- SQLite connections close/reopen; replay remains duplicate across reopened stores.
- Simulated sink outage leaves one pending outbox entry with one attempt.
- Recovery drains the persisted outbox; duplicate sink delivery leaves one alert.

Existing activity/anomaly regressions additionally cover bounded publication,
retry rate, queue limits, worker shutdown/restart and pending-outbox recovery
without new input. This demonstration does not claim an OS-process restart or
Broker/Trigger delivery. Historical Knative evidence retains its original date.

## Module II compatibility and remaining rubric requirements

The 72-test selection covers `test_bronze`, `test_events`, `test_event_generator`,
`test_feature_parity`, `test_features`, `test_historical_features`,
`test_online_features`, `test_trino_history`, `test_internal_job_runner`,
`test_module2_rehearsal`, `test_module2_benchmark`,
`test_spark_development_isolation`, and `test_focus_kafka_smoke`.
It checks Kafka/feature contracts, Bronze, Trino history, stream/rehearsal rules,
Airflow job-runner boundaries, and SEC-022 isolation. It does not re-execute
Kafka, Spark/Delta, Trino/dbt, Flink JVM jobs or Airflow infrastructure. Their
recorded runtime evidence remains historical; no Module II architecture changed.

| Area | Remaining acceptance |
|---|---|
| Module I API/KServe | Recover and verify candidate inputs; explicit exact-model approval; immutable images; real Ready, predictions, fail-closed errors and restart recovery |
| Module I platform | Exact supported platform qualification, gateway/observability, HPA and scale-to-zero runtime evidence; independent review of existing local packet |
| Module II MinIO 10% | Instructor acceptance of SeaweedFS equivalence or maintained MinIO runtime |
| Module II systems 60% | Fresh runtime/scale or cloud acceptance where required; independently inspect Flink dead-letter output |
| Module II cloud 20% / data 10% | Four accepted cloud deployments; strictly >100,000,000,000 bytes reconciled; benchmark remains prohibited in this task |
| Module III technical | Approved KServe runtime; hardened anomaly image rerun through Knative; supported persistent transport and authenticated service boundary |
| Module III practical 35% + 5% | Authorized GKE runtime and MLflow/GCS digest round trip; reviewed budget/plan, identity controls, teardown and cost evidence |
| Submission | Fresh final-flow installation proof and actual demonstration video |
| Deployment runner | M10.3 remains BLOCKED/NO-GO with two recorded HIGH findings; no fresh scan claimed |

## Exact next step and acceptance boundary

First restore the exact locked 500-row input, partition files, metrics and model
from an authorized retained artifact source into this fresh checkout, and compare
the identities above before rerunning training in an isolated output directory.
Recover the separate candidate registry/artifact only if that candidate is selected
for review. Missing originals mean historical reproduction remains blocked.

Before any approval/deployment, prepare a packet containing exact model name/version,
run, dataset/partition digests, registered artifact-tree digest, packaged skops
SHA-256, six-feature schema, evaluation and approval scope. Obtain owner approval
through the existing authenticated approval mechanism; neither registry READY nor
engineering selection suffices. Do not restore disabled release workflows to do so.

Once separately authorized and all platform/security gates pass, acceptance must:
(1) verify image/model digests and approval binding; (2) observe `InferenceService`
Ready; (3) exercise direct six-feature LOW/MEDIUM/HIGH fixtures and authenticated
FastAPI inference; (4) verify unauthorized, malformed, unavailable, missing,
corrupt and mismatched-artifact rejection without fallback; (5) restart serving
and prove recovery with identical provenance; (6) route the same sanitized API
activity through real Broker/Trigger, durable consumer/detector and alert sink,
including replay, bounded retry and recovery. Record exact identities, conditions,
request results and persistent row counts. Cluster creation and execution stop at
that authorization boundary; this report grants no approval.
