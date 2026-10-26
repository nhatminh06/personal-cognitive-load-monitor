# Full rubric demonstration contract

**Future execution contract. As of 2026-10-26 every step below is `NOT VERIFIED` as one continuous GKE demonstration.** Existing local component evidence does not substitute for this recording.

Use one correlation prefix and one evidence directory for the run:

```bash
export DEMO_ID="rubric-$(date -u +%Y%m%dT%H%M%SZ)"
export EVIDENCE_DIR="evidence/$DEMO_ID"
mkdir -p "$EVIDENCE_DIR"
```

Never record tokens, kubeconfig contents, environment dumps or raw sensitive payloads. Commands below are templates that become executable only after PRs #13–#17 define pinned names and scripts.

## Demonstration sequence

| # | Action and future command shape | Expected success | Expected failure proof | Evidence filename | Current status |
|---:|---|---|---|---|---|
| 1 | Generate a bounded synthetic dataset: `uv run python scripts/generate_training_fixture.py ...` | Deterministic row count and manifest SHA-256 | Oversize/invalid parameters fail before writing | `01-dataset-manifest.json`, `01-generator.txt` | **NOT VERIFIED end-to-end** |
| 2 | Ingest through Kafka → Bronze → Delta Silver using the versioned Module II commands | Offsets/checksums and pinned Delta version recorded | Invalid schema rejected/dead-lettered | `02-ingestion.txt`, `02-delta-history.json` | **NOT VERIFIED on GKE** |
| 3 | Submit the compiled KFP package with immutable parameters | KFP returns a run ID | Missing/wrong manifest digest rejects before training | `03-kfp-submit.txt` | **NOT IMPLEMENTED** |
| 4 | Inspect preparation, training and evaluation components via KFP API/UI | Every component succeeds with pinned image digest | Deliberate invalid input component fails and prevents downstream registration | `04-kfp-run.json`, screenshots `04a`–`04d` | **NOT IMPLEMENTED** |
| 5 | Query exact MLflow version and GCS artifact generation | Candidate tags and independently computed artifact-tree digest match | Wrong expected digest is rejected | `05-mlflow-version.json`, `05-gcs-digest.txt` | **NOT VERIFIED with GCS** |
| 6 | Owner approves the exact synthetic-demo model using the explicit approval command | Only named version/digest becomes approved | Newest/candidate/wrong digest cannot be selected | `06-owner-approval.txt` | **BLOCKED by future explicit approval** |
| 7 | Deploy signed image digest and exact approved model through KServe | `InferenceService` becomes Ready | Candidate, unsigned image or wrong digest is rejected | `07-kserve-status.yaml`, `07-image-attestation.json` | **NOT VERIFIED** |
| 8 | POST one valid prediction to FastAPI | Existing response schema returns LOW/MEDIUM/HIGH and no fallback | Invalid/authless request returns bounded 4xx; backend failure returns 503 | `08-predict-success.json`, `08-predict-fail.txt` | **API local only; full path NOT VERIFIED** |
| 9 | Inspect `/model-info`, KServe metrics and correlation data | `inference_source=kserve` and exact provenance match deployment | Any mismatch keeps readiness closed | `09-model-info.json`, `09-kserve-metrics.txt` | **NOT VERIFIED** |
| 10 | Query Knative Broker/Trigger and logging consumer by event/correlation ID | One sanitized event reaches the consumer | Raw input/credential scan finds zero prohibited fields | `10-cloudevent.json`, `10-eventing-status.txt` | **NOT IMPLEMENTED** |
| 11 | Inject a deterministic error/latency/rate/staleness fixture | Rule threshold is crossed reproducibly | Boundary fixture below threshold stays normal | `11-anomaly-input.jsonl` | **NOT IMPLEMENTED** |
| 12 | Inspect detector alert and monitoring | Exactly one alert appears within the SLO with rule/window IDs | Replay produces no duplicate alert | `12-alert.json`, `12-detection-latency.txt`, screenshot `12-dashboard.png` | **NOT IMPLEMENTED** |
| 13 | Show GKE namespaces, workload readiness and immutable images | Required workloads are Ready and images use repository digests | No Spark workload, public service or development credential exists | `13-workloads.txt`, `13-security.txt` | **BLOCKED by cloud authorization/cost** |
| 14 | Trigger one controlled serving/event failure and recover using rollout/rollback | Failure is visible; recovery restores the verified version | No fallback or silent event loss occurs | `14-failure.txt`, `14-recovery.txt` | **NOT VERIFIED** |
| 15 | Save evidence, show billing, and execute reviewed scoped teardown | Evidence index complete; owned resources stop accruing cost | Teardown refuses unknown/unowned targets | `15-evidence-sha256.txt`, `15-cost.txt`, `15-teardown.txt` | **NOT VERIFIED** |

## Future command checklist

Before recording, PR #17 must replace these placeholders with exact commands and immutable identifiers:

```bash
# Cluster identity must be explicit on every kubectl/helm command.
kubectl --kubeconfig "$KUBECONFIG" --context "$GKE_CONTEXT" get pods -A

# KFP submission command supplied by PR #13.
uv run python pipelines/submit_training_pipeline.py \
  --pipeline pipelines/compiled/cogniflow-training.yaml \
  --dataset-manifest "$DATASET_MANIFEST" --pipeline-root "$GCS_PIPELINE_ROOT"

# Model identity must be explicit; never select "latest".
uv run python scripts/approve_model_candidate.py \
  --model-name "$MODEL_NAME" --model-version "$MODEL_VERSION" \
  --expected-digest "$REGISTERED_ARTIFACT_SHA256"

# KServe deployment command supplied by PR #14 and pinned by repository digest.
helm upgrade --install "$SERVING_RELEASE" helm/cognitive-load-monitor \
  --kubeconfig "$KUBECONFIG" --kube-context "$GKE_CONTEXT" \
  --namespace "$SERVING_NAMESPACE" --set-string "image.digest=$IMAGE_DIGEST"

curl --fail-with-body --request POST "$API_URL/predict" \
  --header "X-API-Key: $API_KEY" --header 'Content-Type: application/json' \
  --data @tests/fixtures/prediction-request.json
```

The real run must capture commands without echoing secret values. Store secrets in the approved manager and pass references, not literal CLI arguments.

## Screenshot and evidence checklist

- [ ] KFP graph showing all successful components and immutable run ID
- [ ] MLflow exact model version, candidate/approval transition and GCS artifact URI
- [ ] KServe Ready conditions and digest-pinned custom runtime
- [ ] FastAPI request/response with `inference_source=kserve`
- [ ] Knative Broker and both Trigger conditions Ready
- [ ] Sanitized log event with matching event and correlation IDs
- [ ] Normal detector window and injected anomaly alert
- [ ] Grafana panel with real request/event/anomaly series
- [ ] GKE workload inventory showing namespaces, resources and no Spark
- [ ] Controlled failure, visible error and successful rollback/recovery
- [ ] Billing view and scoped teardown evidence
- [ ] SHA-256 index for exported text/JSON evidence and final video

## Suggested video narration

1. State the synthetic-proxy/non-medical scope and show the commit/digests used.
2. Explain the 60% technical and selected 40% GKE+GCS rubric path.
3. Follow data from generation and ingestion through KFP and MLflow/GCS.
4. Explain the explicit human approval boundary, then show KServe serving through FastAPI.
5. Trace one sanitized CloudEvent through Knative logging.
6. Contrast normal traffic with a reproducibly injected engineering anomaly.
7. Show failure visibility and recovery rather than only the happy path.
8. Close with workload security, actual cost and safe teardown.

Pause on identifiers long enough to read them, but redact account IDs where they are not needed for grading. Do not splice unrelated historical logs to imply a single run.
