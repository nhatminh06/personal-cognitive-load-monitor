# Multimodal focus-session MVP: pre-cloud design

**Status:** design only. This document does not approve a model, change the
Module I compatibility matrix, alter Module III Standard-mode serving, or claim
clinical validity. GKE is outside this milestone.

## Product boundary

CogniFlow estimates the effort a user reports for a bounded programming or
study session. It is an MLOps and data-platform demonstration, not attention
surveillance, diagnosis, productivity scoring, or a psychological assessment.

The MVP predicts an ordinal `effort_rating` from 1 (very low) to 7 (very high)
for a completed five-minute feature window. The label is entered by the user
after the window. For compatibility with the existing serving contract, the
rating is projected to `LOW` (1–2), `MEDIUM` (3–5), or `HIGH` (6–7). The rating,
not the projected band, is the source label. Predictions must say
`self_reported_effort`, never imply measured cognitive state, and show model
and feature provenance.

The system may personalize evaluation after enough sessions exist, but the
first model is population-level. It cannot infer intent, learning quality,
burnout, ADHD, stress, or medical status. Camera features are optional,
environment-sensitive proxies and must not be interpreted as emotion or
identity.

## Repository audit

The audit uses the current working tree and the repository graph. Historical
documents are evidence only for their stated date and scope.

| Area | Existing and reusable | Partial or constrained | New MVP work |
|---|---|---|---|
| FastAPI | Authenticated `/predict`, `/model-info`, `/events`, `/features/{session_id}`, health, readiness, metrics, tracing and a static page in `src/preprocessing_api` | UI is a one-shot four-field prediction form; API is single-tenant | Session lifecycle, label and prediction-history routes plus a session dashboard |
| Model contract | Six ordered `1.0` features, explicit inference modes, no silent fallback, strict `.skops` package validation | Inputs are coarse session snapshots and labels are synthetic proxies | Versioned behavioral/CV feature sets, effort-label provenance and compatibility projection |
| Events | Strict `SessionEvent` v1, Kafka keying, bounded producer retries, dead-letter topic and JSON Schema export | `session.snapshot` is not a lifecycle or feedback contract | New topics and schemas; do not mutate v1 payloads in place |
| Streaming | Kafka 3.9.2, Flink 1.20.5 windows/watermarks/dedup/checkpoints, Redis freshness guard | Computes the original six features only | Join lifecycle/activity/CV windows by session/window and expose v2 online features |
| Batch | SeaweedFS S3, Bronze provenance, Spark/Delta Silver, Trino/dbt Gold and Airflow fixed-command DAG | SeaweedFS is not claimed as MinIO; Spark image is local-only under SEC-022 | Bronze/Silver tables for new contracts and labeled training examples |
| Training | Chronological preparation, leakage checks, candidate models, metrics, KFP v2, MLflow candidate registration | Current fixtures use synthetic proxy labels | Group-aware session/user splitting and three effort experiments |
| Lineage | DVC, dataset/model SHA-256 manifests, MLflow run/version, candidate/approved separation | Current DVC drift must remain visible until resolved | Version every contract, edge asset, feature set, label set and experiment manifest |
| Serving | Local model, KServe custom runtime, Standard/Knative Helm modes, immutable image/model identity | Module I kind PASS is reported but formal review is pending; GKE is untested | Package only an independently accepted MVP model; no automatic approval |
| Event automation | Knative CloudEvents, consumer/DLQ, SQLite dedupe, retry metrics and anomaly outbox | Development transport/auth boundaries are not production-ready | Reuse the delivery pattern locally for notification requests |
| Observability | Prometheus, Grafana, Loki, Tempo, structured logs and trace correlation | Evidence is historical and cloud deployment is absent | Session, edge-agent and Discord delivery metrics with bounded labels |
| CV | None found in source or dependencies | No camera permission, asset or performance contract | Optional separate edge process; off by default |
| Discord | None found | No secret or delivery contract | Optional webhook adapter with mock-only CI |
| Notebooks/CI | Four notebooks, Pytest coverage gate at 81%, Ruff and scoped MyPy | Notebooks describe the old synthetic proxy | Update the existing four in place; retain the gate |

The passing kind evidence directory remains external to Git and immutable. The
repository compatibility matrix remains `BLOCKED`; kind evidence does not imply
GKE compatibility.

## Original requirement mapping

### Module I — MLOps foundation

| Original requirement | Current implementation | MVP treatment |
|---|---|---|
| Python, Pytest and >80% coverage | Python 3.11+, CI Pytest and 81% fail-under | Preserve; new packages enter the same coverage scope |
| Test → build → manual deploy CI/CD | Protected workflows and test dependency | Preserve; MVP local acceptance precedes any image/deploy workflow |
| Four notebooks | EDA, processing, training and deployment notebooks | Keep exactly four; update them for real opt-in session data and the three experiments |
| FastAPI preprocessing API | Strict Pydantic request/response and explicit backend | Extend with session routers; retain `/predict` compatibility |
| MLflow registry | Tracked runs, candidates and separate approval | Log all experiments; register candidates only |
| DVC pipeline | Reproducible data/model/report stages | Add raw-event manifest → labeled windows → experiments; never track images |
| Prometheus/Grafana | Local metrics and dashboards | Add bounded-cardinality session/edge/notification panels |
| Loki/Tempo | Structured logs and OTLP traces | Correlate by pseudonymous session/window/event IDs, never raw activity |
| Evidently | Historical drift report | Monitor numerical feature and prediction drift; labels arrive separately |
| Authentication | Fail-closed production API key | Preserve; local UI uses the same origin/API boundary and never embeds production keys |
| HPA | Bounded FastAPI HPA chart | Preserve source and later runtime acceptance requirements |
| Helm/Kubernetes IaC | Hardened chart, quotas and policies | Add no cloud requirement for MVP; later templates remain digest-pinned |
| KServe | Custom verified `.skops` runtime | Reuse after independent model approval; Module III stays Standard mode |
| Scale-to-zero | Module I Knative overlay and preserved kind 2→0→2 evidence | Preserve code/evidence; formal review and GKE proof remain separate |
| NGINX/TLS | Local auth proof and cloud-static templates | Local MVP binds loopback; no new public endpoint |
| Model retrieval/integrity | Exact package, artifact-tree and OCI digests | Include feature/label/edge-asset manifests in package provenance |
| Security | Non-root, immutable images, no fallback, secret scanning | CV off by default; no frames; Discord secret only at runtime |

### Module II — data engineering and streaming

| Original requirement | Current implementation | MVP treatment |
|---|---|---|
| S3-compatible object storage | SeaweedFS Bronze with checksums | Store versioned JSON event envelopes and aggregates; keep MinIO-equivalence limitation |
| Kafka | Versioned topic, acknowledged producer, session key | Add versioned lifecycle/activity/CV/label/prediction/notification topics |
| Flink | Event-time windows, watermarks, dedupe, checkpoint recovery | Build behavioral and optional CV window joins; preserve late-data handling |
| Redis | Timestamp-protected online projection | Store latest v2 window by session; history stays in Delta |
| Spark + Delta | Validated Bronze→Silver and idempotent merge | Normalize each new contract and materialize labeled window rows locally only |
| Trino + dbt | Silver query and Gold models | Add session quality and experiment-readiness models |
| Airflow | Authenticated fixed-command six-task DAG | Add allowlisted preparation commands only; no arbitrary command input |
| Cross-language parity | Shared Python/Spark/Flink fixture | Add a v2 fixture containing behavior, missing-CV indicator and window timing |
| Observability | API/Flink metrics and dashboard | Add lag, dropped/late window, join completeness and label-delay metrics |
| Dataset >100 GB | Safe generator only; execution deferred | Not needed for MVP and remains an explicit rubric gap |
| Four cloud deployments | Not completed | Unchanged; local MVP makes no cloud claim |

### Module III — distributed ML and automation

| Original requirement | Current implementation | MVP treatment |
|---|---|---|
| Reproducible training pipeline | Six KFP v2 components and candidate registration | Parameterize existing tasks for experiment A/B/C rather than create another orchestrator |
| KServe runtime | Strict custom runtime and FastAPI client | Serve one separately approved winner; keep Standard mode default |
| Knative inference activity | Sanitized CloudEvents, Broker/Trigger, dedupe and DLQ | Prediction events use the new result contract without raw inputs |
| Event-driven anomaly detection | Deterministic windows, outbox, cooldown and metrics | Continue operational anomaly detection; do not reinterpret it as user-state detection |
| GKE/GCS | Static Terraform/readiness only | Deferred; no MVP dependency |
| MLflow cloud registry | Local registry plus static GCS design | Local tracking is sufficient; cloud round trip remains blocked |
| Final evidence/video | Evidence contracts exist; final cloud video absent | Add a local focus-session acceptance packet, not a cloud claim |

## Versioned contracts

Each Kafka payload uses a strict envelope with `schema_version`, `event_id`,
`event_type`, `session_id`, optional pseudonymous `subject_id`, timezone-aware
`event_time` and `ingested_at`, `source`, `producer_version`, and an idempotency
key. Unknown fields fail validation. Contract evolution uses a new schema/topic;
consumers never guess fields from another version.

### 1. Session lifecycle — `cogniflow.session-lifecycle.v1`

`session.started|paused|resumed|completed|cancelled` with monotonically increasing
`sequence`, `session_kind` (`programming|study`), optional bounded
`planned_duration_seconds`, and `privacy_mode` (`behavioral|behavioral_cv`). The
server enforces legal transitions and one terminal event. No project name,
document title or application name is collected.

### 2. Behavioral activity — `cogniflow.behavioral-activity.v1`

One non-overlapping local window with `window_id`, `[window_start, window_end)`,
`active_seconds`, `idle_seconds`, `keyboard_event_count`, `pointer_event_count`,
`application_switch_count`, and optional `build_count`/`test_count`. Counts are
bounded and contain no key values, mouse coordinates, filenames, URLs, window
titles, source code, clipboard data or process lists.

### 3. CV feature window — `cogniflow.cv-features.v1`

One window aligned to the behavioral window: `camera_available`,
`face_presence_ratio`, `gaze_away_ratio`, `blink_rate_per_minute`,
`head_pose_variance`, `frames_sampled`, `frames_processed`, `frames_dropped`,
`agent_version`, `asset_name`, `asset_sha256`, `cpu_seconds`, and latency
percentiles. Values are aggregate numerics. No frame, face embedding, identity,
emotion label or biometric template may enter the API, event bus, logs or disk.
If unavailable, emit `camera_available=false` and null feature values rather than
fabricating zeros.

### 4. Effort label — `cogniflow.effort-labels.v1`

`label_id`, `window_id` or terminal `session_id`, integer `effort_rating` 1–7,
`reported_at`, `applies_to_start/end`, `label_source=user_self_report`, and an
optional 1–5 `confidence`. Labels are append-only corrections: a correction
references `supersedes_label_id`; history is not overwritten.

### 5. Prediction result — `cogniflow.predictions.v1`

`prediction_id`, `window_id`, `predicted_effort_rating` as a bounded float,
`effort_band`, ordered class probabilities, `model_name/version/run_id`, model
and dataset SHA-256, behavioral/CV contract versions, `cv_available`,
`feature_as_of`, and inference latency/source. The compatibility API may expose
the band as the existing `cognitive_load_level`, but metadata must identify the
target as `self_reported_effort`.

### 6. Notification request/result — `cogniflow.notifications.v1`

`notification.requested|delivered|failed|suppressed` with `notification_id`,
`prediction_id`, `rule_id/version`, `channel=discord_webhook`, `deduplication_key`,
attempt count and sanitized outcome. The event never includes the webhook URL,
authorization material or the full prediction feature vector.

Schemas belong in `src/cogniflow_contracts/` with generated JSON Schema under
`docs/focus-session/schemas/`. Existing `SessionEvent` v1 remains valid and
unchanged during migration.

## Minimal local UI and API

Reuse the FastAPI process and static HTML/CSS/JavaScript; do not introduce a
frontend framework. The page contains:

1. Start programming/study session.
2. Pause/resume/end controls and elapsed time.
3. Camera opt-in toggle, off on every new browser load.
4. Current behavioral/CV availability, never camera video.
5. Latest effort estimate with provenance and non-clinical disclaimer.
6. A 1–7 rating form after each configured window and at session end.
7. Local history for the active session and notification opt-in.

Proposed authenticated routes:

| Method/path | Purpose |
|---|---|
| `POST /sessions` | Start and persist a session |
| `POST /sessions/{id}/transitions` | Pause, resume, complete or cancel |
| `POST /sessions/{id}/activity-windows` | Accept bounded local aggregate behavior |
| `POST /sessions/{id}/cv-windows` | Accept optional aggregate CV features |
| `POST /sessions/{id}/labels` | Append a self-reported rating/correction |
| `POST /sessions/{id}/predictions` | Request an estimate from the latest complete window |
| `GET /sessions/{id}` | Current state and privacy settings |
| `GET /sessions/{id}/timeline` | Sanitized local events/results |

Use the existing SQLite repository/outbox style for local session state and
publish accepted events through the existing Kafka adapter when enabled. The
API returns 503 on an unavailable configured dependency; it does not silently
change inference or persistence mode.

## Optional CV edge agent

The edge agent is a separate `cogniflow-edge` process so camera dependencies do
not enter the FastAPI or KServe images. Install it through an optional `cv`
dependency group containing pinned MediaPipe/OpenCV versions.

- Disabled unless the user starts it and opts in for the current session.
- Opens the camera locally, samples at a bounded rate (initially 5 FPS), derives
  landmarks, aggregates a five-minute window, then discards each frame.
- Does not expose a video endpoint, write frames, create embeddings or transmit
  raw landmarks.
- Verifies the exact MediaPipe task/model asset against a committed name,
  upstream URL, license and SHA-256 manifest before use.
- Measures process CPU time, RSS, processed/dropped frames and p50/p95 feature
  latency; acceptance target is median CPU below one logical core and p95 frame
  processing below 150 ms on the documented reference host.
- Camera denial, disconnect, no face or unsupported architecture produces an
  explicit unavailable window and leaves behavioral prediction operational.
- Tests use generated landmark/numeric fixtures or a tiny synthetic frame,
  never webcam recordings.

## ML experiments

All experiments consume the same immutable labeled-window manifest and use the
same split IDs.

| Experiment | Inputs | Minimum models | Purpose |
|---|---|---|---|
| A — behavioral | activity counts, active/idle ratios, session elapsed, original task/deadline fields | Dummy, regularized ordinal/logistic baseline, Random Forest | Establish the useful non-camera baseline |
| B — CV-only | aggregate CV values plus availability/quality indicators | Dummy, regularized baseline, Random Forest | Measure whether optional CV adds signal; never impute missing camera as normal behavior |
| C — multimodal | A + B with explicit missing-CV mask | Regularized early-concatenation baseline and Random Forest | Test incremental value over A without a deep-learning stack |

Primary metrics are macro F1 for the three bands and mean absolute error for the
1–7 rating. Also report balanced accuracy, per-class precision/recall, confusion
matrix, calibration error, prediction coverage with/without CV, inference
latency and performance by subject/session kind when sample sizes permit.
Promotion requires C to beat A on a locked test set by a predeclared practical
margin; otherwise ship A. CV is not a mandatory feature.

### Splitting and leakage controls

- Never randomly split windows from the same session.
- For multiple users, hold out entire pseudonymous subjects for the final test;
  within development subjects, use chronological session groups for train and
  validation.
- For a single-user MVP, use expanding-window chronological splits by complete
  session and describe the result as personal, not population generalization.
- Fit scalers, imputers and feature selection on train only.
- A label may join only after its `reported_at` and cannot become an input to
  the prediction it evaluates.
- Keep adjacent windows, corrected labels and duplicates in one split group.
- Freeze the split manifest before model comparison; the test set is evaluated
  once for the selected candidate.

Each MLflow run records experiment type, contract/feature versions, split
manifest digest, DVC data revision, Git SHA, dependency lock digest, parameters,
metrics, confusion/calibration artifacts and model-package digest. DVC stages
produce Bronze manifests, aligned labeled windows, frozen splits and evaluation
reports. Evidently compares numerical distributions and missingness against the
training reference; label/performance drift is reported only when delayed user
ratings exist. A model package retains the existing strict manifest and adds
target, feature-set, split and optional edge-asset identities.

## Discord integration

Discord is an optional subscriber, not part of the prediction request path.
The user enables a versioned rule such as “notify after two consecutive HIGH
windows with confidence above threshold.” A notification-request event enters
the existing transactional outbox pattern.

- Read `DISCORD_WEBHOOK_URL` only from the process environment or mounted
  secret; redact it from logs and errors.
- Require HTTPS and the expected Discord webhook host; never accept a webhook
  URL from an event payload.
- Use a short connect/read timeout, at most three delivery attempts, exponential
  backoff with jitter, and honor bounded `Retry-After` on HTTP 429.
- Deduplicate on `rule_version:prediction_id:channel` in SQLite locally and use
  an expiry appropriate to the session retention policy.
- Treat 2xx as delivered, 429/5xx/network errors as retryable, and other 4xx as
  terminal; exhausted attempts emit a sanitized failed event.
- Export request/delivery/suppression/failure counters and latency histograms;
  trace by notification and prediction IDs.
- CI uses `httpx.MockTransport` or a local mock server. It never contacts
  Discord and never requires a real secret.

## Ordered PR roadmap

### PR 1 — target and contracts

- **Goal:** establish semantics and six strict v1 contracts without runtime changes.
- **Files:** create `src/cogniflow_contracts/`, generated schemas and contract tests; update data/model cards.
- **Reuse:** Pydantic `extra=forbid`, timezone validation, UUIDs and schema exporter.
- **Tests:** valid/invalid versions, bounds, transitions, null CV, forbidden raw fields, schema snapshots.
- **Accept:** contracts and JSON Schemas are deterministic; existing SessionEvent tests remain green.
- **Dependencies:** none.
- **Risk/rollback:** schema churn; revert additive files because existing topics are untouched.

### PR 2 — local session state and API

- **Goal:** create/pause/resume/complete sessions and append effort labels.
- **Files:** add `preprocessing_api/sessions.py`, `cogniflow_sessions/` SQLite repository; compose router in `main.py`.
- **Reuse:** authentication, security middleware, SQLite transaction/dedupe patterns, observability.
- **Tests:** legal/illegal transitions, auth, idempotency, correction lineage, restart recovery, dependency failure.
- **Accept:** one local session survives API restart and produces ordered lifecycle/label events.
- **Dependencies:** PR 1.
- **Risk/rollback:** local state migration; version the SQLite schema and retain export before rollback.

### PR 3 — behavioral collection and data paths

- **Goal:** ingest behavioral windows and materialize online/offline v2 features.
- **Files:** extend Kafka adapter/topics, Flink job/tests, Bronze/Spark schemas, Redis record, parity fixture and dbt models.
- **Reuse:** acknowledgment, watermark, dedupe, checkpoint, stale-write and Delta merge logic.
- **Tests:** cross-language parity, late/duplicate windows, bounds, restart, stale Redis rejection and idempotent Delta replay.
- **Accept:** a synthetic session reaches Redis and Delta with matching window values and provenance.
- **Dependencies:** PRs 1–2.
- **Risk/rollback:** destabilizing v1; use new topics/keys/tables and disable only v2 consumers.

### PR 4 — optional CV edge agent

- **Goal:** emit aggregate CV windows locally with measurable resource use.
- **Files:** add `src/cogniflow_edge/`, optional `cv` dependencies, asset manifest and operator guide.
- **Reuse:** contract client, checksums, metrics and bounded HTTP behavior.
- **Tests:** generated fixtures, asset digest mismatch, no-camera/no-face, API timeout, no frame serialization and performance harness.
- **Accept:** opt-in fixture produces one numeric window; disabled/missing camera keeps behavioral flow healthy; no image bytes appear in captures/logs.
- **Dependencies:** PR 1; can proceed alongside PR 3.
- **Risk/rollback:** native dependency/CPU variance; uninstall optional group and disable agent without affecting API.

### PR 5 — labeled datasets and three experiments

- **Goal:** create immutable split manifests and compare A/B/C reproducibly.
- **Files:** extend `historical.py`, `training.py`, KFP task parameters, DVC stages and the existing four notebooks.
- **Reuse:** point-in-time joins, chronological validation, candidate models, MLflow and DVC digests.
- **Tests:** subject/session leakage, label availability, frozen split parity, missing CV, metric determinism and candidate-only registration.
- **Accept:** all three runs share exact split IDs; report A/B/C plus dummy; no model is approved.
- **Dependencies:** PRs 3–4 and enough opt-in labels; A can run before PR 4.
- **Risk/rollback:** insufficient data or CV adds no value; retain A and record B/C as negative experiments.

### PR 6 — packaging and local serving

- **Goal:** package one reviewed experiment candidate and serve it locally without weakening identity checks.
- **Files:** extend package manifest/model card, feature adapter and KServe runtime tests; preserve Helm mode defaults.
- **Reuse:** `validated_package_manifest`, MLflow approval boundary, `.skops` runtime and model metadata.
- **Tests:** exact package loads; wrong target/feature/split/model digest fails; missing CV follows declared model policy; Standard render unchanged.
- **Accept:** local-model prediction and metadata match the reviewed package; KServe deployment still requires separate approval.
- **Dependencies:** PR 5 plus independent candidate review.
- **Risk/rollback:** contract incompatibility; restore previous exact model/image digest.

### PR 7 — focus-session dashboard

- **Goal:** make the complete local session loop usable without a frontend stack.
- **Files:** update `static/index.html` and API/UI tests; add accessible session timeline and privacy copy.
- **Reuse:** current static FastAPI page, same-origin requests and auth behavior.
- **Tests:** API contract, DOM/static assertions, keyboard/accessibility smoke, camera default-off and error states.
- **Accept:** start → activity → prediction → rating → complete works locally; UI never displays or uploads video.
- **Dependencies:** PRs 2–3 and optionally 4/6.
- **Risk/rollback:** page regression; retain endpoint compatibility and revert the single static asset.

### PR 8 — private Discord notifications

- **Goal:** deliver opt-in, deduplicated notification events outside the prediction path.
- **Files:** add `src/cogniflow_notifications/`, rule config, local worker/Compose service and dashboard metrics.
- **Reuse:** CloudEvent schema, transactional outbox, SQLite dedupe, retry/DLQ and tracing patterns.
- **Tests:** mocked 2xx/4xx/429/5xx/timeouts, bounded retry, Retry-After cap, dedupe, redaction and disabled mode.
- **Accept:** one eligible fixture delivers once to a mock; replay is suppressed; no secret appears in evidence.
- **Dependencies:** PRs 1 and 6; Knative deployment is not required locally.
- **Risk/rollback:** notification spam/secret exposure; disable worker/rule, rotate webhook, retain sanitized audit rows.

### PR 9 — local end-to-end acceptance

- **Goal:** prove the complete MVP locally and index evidence without changing cloud or kind qualification.
- **Files:** add an opt-in rehearsal script, fixture, evidence validator and operator documentation.
- **Reuse:** existing Module I/II rehearsal safety gates and evidence hashing.
- **Tests:** preflight, interruption/retry, missing optional camera, mock Discord, evidence tamper rejection and cleanup scope.
- **Accept:** a fresh local profile completes the flow below; CI remains above 81%; four notebooks execute; Module III renders Standard mode.
- **Dependencies:** PRs 1–8, with CV and Discord tested both enabled and disabled.
- **Risk/rollback:** resource contention; isolated Compose profile, explicit ports/volumes and separately authorized cleanup.

## Local end-to-end acceptance

Use a new Compose profile, new volume prefix, synthetic camera fixture and mock
Discord server. Do not use GKE or either existing kind cluster.

1. Record Git SHA, lockfile, contract schemas, asset/model/dataset digests and host resources.
2. Start the existing observability, Kafka, SeaweedFS, Redis, Flink, Spark/Delta,
   Trino/dbt, MLflow and FastAPI components with bounded resources.
3. Verify authentication, health/readiness, Prometheus targets, logs and traces.
4. Start a programming session; reject an illegal transition and duplicate event.
5. Publish deterministic behavioral windows; optionally run the synthetic CV fixture.
6. Verify Kafka offsets, Flink window/watermark state, Redis v2 projection and
   Bronze/Delta/Trino parity.
7. Request a prediction; verify target, feature timestamp, missing-CV behavior,
   exact model/run/package identity and no fallback.
8. Submit a 1–7 rating after prediction and prove the point-in-time join does not
   leak it into that prediction.
9. Trigger one opt-in notification against the mock Discord endpoint; replay it
   and prove exactly one side effect plus bounded retry evidence.
10. Confirm Grafana panels, a sanitized Loki log, a correlated Tempo trace and
    bounded metric label cardinality.
11. Run DVC reproduction, A/B/C experiment fixture, MLflow candidate-only checks,
    Evidently report, package tamper negatives and all four notebooks.
12. Run full Pytest coverage, Ruff, MyPy, Java tests, schema compatibility,
    Compose/Helm rendering, secret scan and Module III Standard-mode regression.
13. Hash a fresh evidence directory containing no secrets or images. Stop the
    isolated profile without deleting volumes; cleanup requires a separate target review.

Failure at any step preserves evidence and stops downstream claims. Acceptance
proves only the local MVP. It does not qualify GKE, approve a model, accept the
Module I compatibility matrix, or replace the independent kind evidence review.

## Complexity controls

- Keep the current FastAPI page; no React, mobile application or user account system.
- Use classical tabular baselines; no deep multimodal network, GPU or feature store addition.
- Keep Kafka/Flink/Spark because they are project requirements, but keep them off
  the synchronous prediction path.
- Keep CV and Discord as independently disabled adapters.
- Do not deploy Knative Eventing merely to send a local Discord request; use the
  same event/outbox contract locally and preserve Knative for Module III acceptance.
- Prefer the behavioral model unless CV demonstrates a reproducible improvement.
- Do not add raw telemetry fields “for later”; new collection requires a privacy
  and contract review.
