# Phase 7: Knative real-time inference-health anomaly detection

**Verification date:** 2026-10-26 (America/Chicago) / 2026-10-27 UTC. **Scope:** deterministic service-health anomalies over the existing sanitized activity CloudEvent. This detector does not identify medical, psychological, or cognitive anomalies. All demonstration provenance is `synthetic_demo`.

## Architecture

```mermaid
flowchart LR
    Broker[cogniflow-v1 Broker] --> Logging[existing logging Trigger]
    Broker --> Trigger[inference-anomaly-v1 Trigger]
    Trigger --> Detector[SQLite-backed detector]
    Detector -->|transactional outbox| Sink[SQLite alert sink]
    Detector --> Metrics[Prometheus / Grafana]
    Trigger -->|3 retries exhausted| DLQ[existing dead-letter sink]
```

The second Trigger filters the stable `org.cogniflow.inference.activity.v1` type and does not alter the original logging Trigger. The detector reuses the same strict parser. A single SQLite transaction deduplicates `(source,id)`, retains bounded event state, evaluates rules, persists alert decisions and appends the outbox. The sink is internal-only and deduplicates `(source,id)` again.

## Demonstration rule contract

These deliberately small thresholds are for deterministic local evidence, not production alert policy.

| Rule ID / version | Sliding window | Minimum | Trigger | Cooldown | Normal / boundary / anomaly |
|---|---:|---:|---|---:|---|
| `inference_error_ratio` / `1.0` | 60 s | 4 | error ratio `>= 0.5` | 60 s | below 0.5 / exactly 0.5 alerts / above alerts |
| `inference_mean_latency_ms` / `1.0` | 60 s | 3 | mean latency `>= 500 ms` | 60 s | below 500 / exactly 500 alerts / above alerts |
| `inference_request_count` / `1.0` | 60 s | 6 | request count `> 5` | 60 s | five or fewer / five does not alert / six alerts |

Windows use event time and are evaluated at each accepted event. Events up to 10 seconds behind the greatest observed event time are accepted; older events are acknowledged as late and excluded. State is retained for one hour and capped at 10,000 records. The oldest records are removed first. Duplicate deliveries do not change state. A rule/backend alert inside its cooldown is counted as suppressed.

Feature staleness is intentionally absent: activity schema `1.0` contains no validated feature timestamp. Inferring it from request time, model identity, latency or raw features would be misleading and would weaken the privacy contract.

## Alert contract

Type `org.cogniflow.inference.anomaly.v1`, schema `1.0`, source `urn:cogniflow:anomaly-detector`. The deterministic anomaly ID is SHA-256 of rule ID/version, backend and triggering event ID. Payload fields are limited to anomaly/rule identity, UTC detection and window timestamps, backend category, observed metric, threshold/operator, sample count, severity, triggering event ID and `synthetic_demo` provenance. Credentials, correlation IDs, request inputs, IP addresses, private identifiers and medical conclusions are excluded.

## Failure and recovery

Alert publication occurs only after the state transaction commits. Failed publication increments the outbox attempt count, leaves `published_at` empty and returns HTTP 503 so Knative retries. Duplicate input delivery still flushes the existing outbox; a sink acknowledgement marks the entry published. Therefore a crash between state commit and publication cannot silently discard the alert. Delivery is at-least-once and both endpoints are idempotent.

The development Broker still uses `InMemoryChannel`; queued activity events may be lost with its dispatcher or node. Production requires a persistent supported channel, authenticated workload-to-workload transport, production thresholds, retention review and an externally durable database.

## Local deployment and verification

Use only a separately owned disposable `cogniflow-eventing` kind cluster. Do not target `cogniflow-local`.

```bash
docker build -f Dockerfile.anomaly-detector -t cogniflow-anomaly-detector:dev .
kind load docker-image cogniflow-anomaly-detector:dev --name cogniflow-eventing
kubectl --kubeconfig /tmp/cogniflow-eventing-kubeconfig apply \
  -f deploy/knative/anomaly.yaml -f deploy/knative/anomaly-trigger.yaml
kubectl --kubeconfig /tmp/cogniflow-eventing-kubeconfig \
  -n cogniflow-eventing get broker,trigger,pods,pvc
kubectl --kubeconfig /tmp/cogniflow-eventing-kubeconfig \
  -n cogniflow-eventing port-forward service/anomaly-detector 18016:80 \
  --address 127.0.0.1
```

The manifest's `:dev` tag and `imagePullPolicy: Never` are permitted only for the disposable local proof. Runtime evidence must record the container runtime's resolved image ID. Cloud deployment requires a signed repository digest and attestation; a Docker image ID is not a repository digest.

The local event-to-alert target is **under 2 seconds** from the triggering activity CloudEvent time to the persisted sink alert.

## Actual isolated runtime evidence

| Check | Observed result |
|---|---|
| Knative | Eventing `1.23.0`; Broker and both logging/anomaly Triggers `Ready=True` |
| Rules | Exactly one error alert at ratio `0.5`, one latency alert at `500 ms`, and one rate alert at count `6` |
| Normal/boundary | Low-latency success traffic did not alert; threshold semantics matched the table |
| Exact final-image run | Six Broker events produced rate alert `67b78b4a…e07c`; trigger event `b8f87fee…ae18` |
| Detection latency | Exact final run: `3.558 ms` from trigger event time to alert decision; target `<2 s` passed |
| Dedup/restart | Replay kept 13 events/3 alerts; detector and sink Pod replacement retained PVC-backed state |
| Outbox recovery | Sink with no endpoints produced HTTP 503, one pending row and recorded attempts; sink restore plus exact replay cleared backlog to zero |
| Existing logger | Original logging Trigger remained Ready and persisted 15 unique Broker events during the full acceptance run |
| Metrics/dashboard | Prometheus `up=1`; live generated/suppressed/publication-failure series queried; Grafana provisioned UID `cogniflow-anomaly-v1` and returned live outbox `0` |
| Resource snapshot | kind node `1.476 GiB`, `8.99%` CPU; temporary Prometheus `23.88 MiB`; Grafana `53.32 MiB` |
| Final image | Docker content ID `sha256:2e44e6149af1…`; loaded runtime image ID `sha256:ab341f997970…`; neither is represented as an OCI repository digest |
| Security scan | Trivy `0.67.2`: zero fixable High/Critical Debian or Python findings |
| Cleanup | Temporary Prometheus/Grafana stopped and disposable cluster deleted; only `cogniflow-local` remained |

The full three-rule run used the immediately preceding image, then readiness/configuration and record-retention guards were added. The exact final image was rebuilt, scanned, constraint-smoked, loaded into a fresh disposable Knative cluster and verified through the Broker with a persisted rate alert. No production repository digest, signature or attestation was created; those remain cloud-release gates.

Rollback deletes only `inference-anomaly-v1`, `anomaly-detector`, `anomaly-alert-sink` and their explicitly owned PVCs after evidence retention. It must not remove the Broker, original logging Trigger, shared cluster, Terraform state, PersonalOS, or Docker volumes. The isolated verification cluster was separately owned and was deleted in full after evidence capture.

## Local quality checks

```bash
uv run pytest src/tests/test_anomaly_detection.py
uv run pytest src/tests --cov=src/preprocessing_api --cov=src/cogniflow_data \
  --cov=src/cogniflow_eventing --cov=src/cogniflow_anomaly --cov-fail-under=81
uv run ruff check .
MYPYPATH=src uv run mypy --explicit-package-bases --ignore-missing-imports \
  src/preprocessing_api src/cogniflow_data src/cogniflow_eventing src/cogniflow_anomaly
```
