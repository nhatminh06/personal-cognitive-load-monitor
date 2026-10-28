# Focus-session v1 contracts

These additive contracts implement PR 1 of the pre-cloud multimodal MVP. They
do not replace `SessionEvent` v1, the six-feature model contract, or the current
prediction API. The authoritative Python models are in
`src/cogniflow_contracts`; committed JSON Schemas are in `schemas/`.

## Prediction target

`self_reported_effort` is the effort rating a user supplies after one completed,
exactly five-minute window. The integer rating from 1 through 7 is ground truth.
`LOW`, `MEDIUM`, and `HIGH` are derived compatibility metadata:

| Rating | Band |
|---:|---|
| 1–2 | `LOW` |
| 3–5 | `MEDIUM` |
| 6–7 | `HIGH` |

For continuous predictions, the deterministic half-step boundaries are
`[1, 2.5) → LOW`, `[2.5, 5.5) → MEDIUM`, and `[5.5, 7] → HIGH`. A prediction may
omit class probabilities. When probabilities are present, they are ordered
`LOW, MEDIUM, HIGH`, each is finite and in `[0, 1]`, and their sum is 1.

This is a prediction of a self-report, not a clinical, psychological or
objective cognitive-load measurement.

## Common envelope and topics

Every event has strict schema version `1.0`, UUID event identity, validated
session and optional pseudonymous subject identities, UTC event/ingestion
timestamps, bounded source/producer values and an idempotency key. Unknown
fields are rejected.

| Topic | Event model |
|---|---|
| `cogniflow.session-lifecycle.v1` | `SessionLifecycleEvent` |
| `cogniflow.behavioral-activity.v1` | `BehavioralActivityEvent` |
| `cogniflow.cv-features.v1` | `CvFeatureWindowEvent` |
| `cogniflow.effort-labels.v1` | `EffortLabelEvent` |
| `cogniflow.predictions.v1` | `PredictionResultEvent` |
| `cogniflow.notifications.v1` | `NotificationEvent` |

The lifecycle collection validator requires sequence 1 `session.started`,
strictly increasing contiguous sequence numbers, nondecreasing event time,
stable session metadata, legal transitions and no event/idempotency duplicates.
Completed or cancelled sessions are terminal.

Behavioral and CV events cover `[window_start, window_end)` where the duration
is exactly five minutes. `feature_cutoff`, `feature_as_of` and `window_end` are
the same UTC instant. Behavioral/CV observations cannot occur after ingestion.

## Temporal and leakage rules

1. Only features with timestamps at or before `feature_cutoff` may enter a
   prediction.
2. Prediction `feature_as_of` equals the target window end. Its event time is
   at or after that cutoff.
3. A label is valid only after its complete target window. Delayed labels are
   valid and may arrive out of order.
4. `label_window_ids_used` records historical label windows consumed by a
   prediction. It must contain unique IDs and cannot contain the target
   `window_id`.
5. Training/evaluation must keep corrected labels and all windows from the same
   session in one split. Labels join only when `reported_at` is no later than
   the evaluation cutoff.
6. A correction is a new event referencing the latest prior label for the same
   window. It never mutates or deletes the original event.

## Local PR 2 API and window semantics

The authenticated local API implements `POST /sessions`,
`POST /sessions/{id}/transitions`, `POST /sessions/{id}/labels`,
`GET /sessions/{id}`, and `GET /sessions/{id}/timeline`. Requests use the
existing `X-API-Key` header. The local store retains only a SHA-256 fingerprint
of that key as the session owner; API keys are never returned or written to the
event timeline.

Completed label-eligible windows are consecutive five-minute intervals wholly
inside an active `started` or `resumed` segment. Pausing ends the current active
segment and discards any partial interval; resuming begins a new interval.
Completing or cancelling materializes only whole intervals completed before the
terminal event. A delayed label remains valid after its window completes.
Corrections append a new event and must reference the latest label for the same
window.

The timeline accepts `limit` (1–100, default 50) and a non-negative `offset`.
Lifecycle and label events are committed with a durable outbox row in the same
SQLite transaction. PR 2 does not publish that outbox: a null `published_at`
means persisted locally and awaiting the PR 3 Kafka adapter.

## Local PR 3 behavioral pipeline

`POST /sessions/{id}/activity-windows` accepts the strict
`BehavioralActivityEvent` contract only for a completed window already
materialized by the owning session. One immutable activity event is allowed per
window. Identical retries return the stored event; reused event, idempotency, or
window identities with different content return a conflict.

The SQLite transaction appends the activity event and its outbox row together.
`scripts/publish_focus_outbox.py` drains at most 25 ordered records per run,
uses the session ID as the Kafka partition key, and marks a row published only
after the existing producer receives an `acks=all` acknowledgement. Producer
retries are bounded at five with 200 ms backoff. A failure increments the
durable attempt count and stops the batch; a process crash leaves the row
pending. Delivery is therefore at least once, not exactly once.

Flink consumes `cogniflow.behavioral-activity.v1` independently of the original
snapshot topic. It validates exact five-minute boundaries, assigns the contract
window end as event time, deduplicates event IDs in checkpointed state, and
quarantines invalid input without copying raw payloads. Events behind the
current watermark are quarantined rather than rewriting an already materialized
feature. Accepted records project one `cogniflow.behavioral-features.v1` record
without combining sessions or active segments.

Redis stores the latest projection at
`cogniflow:behavioral-features:v1:{session_id}` for one hour. A Lua compare and
set accepts only a strictly newer `feature_cutoff`, so duplicate and replayed
older windows cannot replace current state. Optional build/test counts remain
null when unobserved; they are never fabricated as zero.

SeaweedFS Bronze uses immutable `behavioral_activity/schema_version=1.0/`
objects with checksums and Kafka position lineage. Spark writes deduplicated
rows to `s3a://cogniflow-lakehouse/silver/behavioral_features`, partitioned by
the UTC window-end date. The shared Python projection is the offline parity
specification; it contains no effort label fields and exposes only values at the
window's `feature_cutoff`.

### Kafka acceptance smoke test

The isolated smoke harness creates a fresh SQLite database, generates an
ephemeral API key when none is supplied, and drives the real FastAPI routes in
process. It creates and completes a session, submits one valid activity window,
retries the identical request, verifies one activity row plus one pending
outbox row, publishes the ordered outbox through the acknowledged Kafka
producer, and consumes the matching event ID and session partition key from
`cogniflow.behavioral-activity.v1`.

The harness refuses an existing database path and prints only pseudonymous
identifiers, Kafka coordinates, counts, and delivery status. It does not print
the API key or event payload. In Fish, with only the ingestion profile's Kafka
broker running:

```fish
docker compose -f infra/module2/docker-compose.yml --profile ingestion run --rm kafka-init
set smoke_db (mktemp --tmpdir cogniflow-pr3-smoke.XXXXXX.sqlite3)
rm $smoke_db
env PYTHONPATH=src .venv/bin/python scripts/smoke_focus_kafka.py \
  --database $smoke_db --brokers 127.0.0.1:29092
```

The `mktemp` file is removed before execution because the harness deliberately
requires a path that does not exist. Re-running uses a new path and consumer
group; it never deletes topics, broker data, or another Compose project's
resources.

### Flink and Redis acceptance smoke test

The live harness extends the Kafka check through the real Flink job and Redis
freshness script. It creates two completed five-minute windows, verifies the
newer projection, retries the same event, and sends the older window after the
watermark to verify the DLQ and that Redis keeps the fresher value. Evidence is
limited to identifiers, Kafka coordinates, counts, and status; credentials and
event payloads are not printed.

Use only the three required services alongside the existing Kafka broker:

```fish
docker run --rm -v (pwd):/workspace \
  -v cogniflow-maven-cache:/root/.m2 \
  -w /workspace/infra/module2/flink \
  maven:3.9.11-eclipse-temurin-17 mvn -q test package
docker compose -f infra/module2/docker-compose.yml build flink-jobmanager
docker compose -f infra/module2/docker-compose.yml \
  --profile streaming --profile ingestion up -d --no-deps \
  redis flink-jobmanager flink-taskmanager
docker compose -f infra/module2/docker-compose.yml \
  --profile streaming --profile ingestion run --rm --no-deps \
  -e FLINK_OUT_OF_ORDER_SECONDS=2 flink-submit

set smoke_db (mktemp --tmpdir cogniflow-pr3-flink.XXXXXX.sqlite3)
rm $smoke_db
env PYTHONPATH=src .venv/bin/python scripts/smoke_flink_redis.py \
  --database $smoke_db --brokers 127.0.0.1:29092

docker compose -f infra/module2/docker-compose.yml restart flink-taskmanager
docker compose -f infra/module2/docker-compose.yml stop \
  redis flink-jobmanager flink-taskmanager
```

TaskManager recovery can restore an in-process checkpoint while the JobManager
stays alive. The current Compose configuration has no durable external
checkpoint path, so a JobManager or full-stack restart is not checkpoint
recovery evidence.

## Missing camera semantics

When `camera_available=false`, all CV features and asset identity fields are
null and every frame count is zero. This is different from observed zero
behavior. When the camera is available, all aggregate features, timing metrics,
frame reconciliation and immutable asset identity are required.

No contract contains a field for images, landmarks, embeddings, keystroke
contents, source code, clipboard data, window titles, URLs, filenames, Discord
webhook URLs or credentials. Strict unknown-field rejection prevents those
values from entering these event envelopes.

## Examples

Minimal behavioral window fields, in addition to the common envelope:

```json
{
  "event_type": "behavioral.window",
  "window_id": "10000000-0000-0000-0000-000000000001",
  "window_start": "2026-10-28T12:00:00Z",
  "window_end": "2026-10-28T12:05:00Z",
  "feature_cutoff": "2026-10-28T12:05:00Z",
  "active_seconds": 240,
  "idle_seconds": 60,
  "keyboard_event_count": 120,
  "pointer_event_count": 30,
  "application_switch_count": 2
}
```

Missing-camera fields, in addition to the common window envelope:

```json
{
  "event_type": "cv.window",
  "camera_available": false,
  "frames_sampled": 0,
  "frames_processed": 0,
  "frames_dropped": 0,
  "agent_version": "1.0.0"
}
```

Prediction-specific fields may omit probabilities:

```json
{
  "event_type": "prediction.completed",
  "target_name": "self_reported_effort",
  "predicted_effort_rating": 5.49,
  "effort_band": "MEDIUM",
  "class_probabilities": null,
  "feature_as_of": "2026-10-28T12:05:00Z",
  "label_window_ids_used": []
}
```

Regenerate schemas deterministically from the repository root:

```bash
python scripts/export_focus_session_schemas.py
```
