# Phase 5: KServe inference

**Status (2026-10-26): implementation and static/local protocol verification complete; approved-model deployment blocked.**

### Recorded local evidence

- Kubernetes `v1.36.1`, cert-manager `v1.18.2`, KServe CRD/resources and Python
  SDK `v0.20.0` were pinned. Chart digests were recorded during installation.
- A separately owned `cogniflow-kserve` kind cluster ran the KServe controller
  `1/1` Ready in Standard mode. A clearly labeled non-model `InferenceService`
  contract responder reached `Ready=True` at its internal ClusterIP address.
  Its repository-digest-pinned image, restricted pod security and loopback-only
  request were verified. Peak kind-node memory was approximately 1.37 GiB.
- Port `18002` was already occupied locally, so this disposable check used
  `127.0.0.1:18014`; no existing process was changed.
- Separately, the real KServe 0.20 Python ModelServer loaded a disposable trusted
  synthetic `.skops` model, returned verified metadata and V1 predictions, and
  FastAPI `/ready`, `/model-info` and `/predict` succeeded through it. Packaged
  model bytes were verified against their disposable SHA-256 manifest value.
- The disposable cluster and processes were stopped afterward; only
  `cogniflow-local` remained. No approved candidate, production image, cloud
  service or existing cluster was changed.
- The hardening pass rechecked the exact KServe 0.20 probe contract without a
  model artifact or Kubernetes deployment: `/` returned HTTP 200 with
  `{"status":"alive"}`, and `/v1/models/probe-contract` returned HTTP 200 only
  after the in-memory probe model's readiness flag was true. Unit coverage also
  proves the readiness route rejects a non-ready model.

This proves the controller, CRD, Standard-mode reconciliation, internal Service
and process-level API contracts. The contract responder is deliberately not a
model. It does **not** satisfy approved-model KServe acceptance.

## Architecture and version contract

```text
client -> FastAPI /predict -> KServe V1 HTTP
       -> InferenceService -> CogniFlow ModelServer
       -> verified .skops bytes -> LOW | MEDIUM | HIGH
```

This phase pins KServe controller and Python SDK `v0.20.0`. Standard mode was
selected because it uses Kubernetes Deployments and Services without requiring
Knative. KServe 0.20 requires Kubernetes 1.32 or later; the disposable-local
target is Kubernetes 1.36.1. Standard mode does not demonstrate HTTP
scale-to-zero. Only cert-manager and the pinned KServe controller/CRDs are
controller prerequisites.

The KFP demonstration registry was deleted with its disposable cluster. Its
candidate artifacts are evidence only and cannot be reused. No currently
available model package is both explicitly approved and reproducibly retrievable,
so this phase does not build or deploy a model image.

## Trust boundary

Create a package only from an explicitly approved registry version:

```bash
uv run python scripts/package_approved_model.py \
  --tracking-uri http://127.0.0.1:5000 \
  --model-name "$MODEL_NAME" --version "$MODEL_VERSION" \
  --expected-artifact-digest "$REGISTERED_ARTIFACT_SHA256" \
  --output-dir build/model-package
```

The packager verifies the registry identity, `approval_status=approved`, approval
actor/time, exact registered artifact-tree SHA-256, `MLmodel` skops format and
training lineage without deserializing the model. The resulting manifest records
approval status, both artifact digests, dataset digest, exact feature order,
schema `1.0`, Git revision and run ID. The KServe process verifies those values
and the packaged bytes before calling `skops.io.load` with the fixed trusted-type
allowlist. Missing, candidate, corrupt or mismatched packages fail startup.

## Immutable image workflow

`Dockerfile.kserve` intentionally fails at `COPY` when `build/model-package` is
absent. After an owner approves one exact model and digest:

```bash
docker build -f Dockerfile.kserve -t cogniflow-kserve:phase5 .
docker tag cogniflow-kserve:phase5 localhost:5001/cogniflow-kserve:phase5
docker push localhost:5001/cogniflow-kserve:phase5
docker buildx imagetools inspect localhost:5001/cogniflow-kserve:phase5
```

Record the registry's `repo@sha256:...` digest, not a Docker image ID. Resolve
that same repository digest from the target container runtime before replacing
the all-zero documentation sentinel in the Phase 5 values file. With a direct
kind load, `imagePullPolicy: Never` is allowed only after verifying the image's
RepoDigest inside the kind node; never substitute the image ID.

## Isolated deployment

The target cluster is a separately owned disposable cluster named
`cogniflow-kserve`; never use `cogniflow-local`. Install reviewed KServe 0.20 CRDs
and controller in Standard mode, then deploy into `cognitive-load-kserve`:

```bash
kubectl --context kind-cogniflow-kserve apply -f kserve/namespace.yaml
helm --kube-context kind-cogniflow-kserve upgrade --install cognitive-load-kserve \
  helm/cognitive-load-monitor --namespace cognitive-load-kserve \
  -f helm/cognitive-load-monitor/values.phase5-kserve-local.yaml
kubectl --context kind-cogniflow-kserve -n cognitive-load-kserve \
  get inferenceservice,pod,service,event
```

The release is ClusterIP-only, uses a dedicated service account, non-root UID
10001, a read-only root filesystem, dropped capabilities, bounded resources and
an immutable image reference. It has no Ingress, NodePort, cloud credential or
Spark component. kindnet does not enforce NetworkPolicy, so local isolation is
process/cluster/ClusterIP based, not a claim of network-policy enforcement.

Use loopback-only forwards. `18002` is reserved for direct KServe testing; the
FastAPI integration retains `18001`. PersonalOS `8000` and CogniFlow `18000` are
untouched.

```bash
kubectl --context kind-cogniflow-kserve -n cognitive-load-kserve \
  port-forward --address 127.0.0.1 service/cognitive-load-classifier-predictor 18002:80
curl --fail http://127.0.0.1:18002/v1/models/cognitive-load-classifier
```

FastAPI uses one explicit internal origin, rejects redirects, applies a bounded
timeout and validates the exact response keys plus model identity, version,
registered/packaged/dataset digests, schema, feature order and synthetic-label
provenance. `/ready` performs a live verified metadata request. `/model-info`
returns that verified provenance. Any outage or mismatch is a visible failure;
there is no fallback to `local_model` or `demo_rule`.

KServe 0.20 serves liveness at `/` (`200` with `{"status":"alive"}`) and
model readiness at `/v1/models/<name>` (`200` only after `model.ready` is true).
The Helm probes use those exact endpoints. The metadata route is not
application-authenticated: it is reachable to workloads that can reach the
internal ClusterIP service. Its response contains only non-secret model lineage,
never credentials or prediction request payloads. FastAPI remains authenticated
in production and verifies every metadata value before reporting readiness or
accepting a prediction. A production cluster must enforce the intended caller
boundary with a working NetworkPolicy implementation or equivalent service-mesh
policy; kindnet alone does not provide that enforcement.

The checked-in Phase 5 values contain all-zero documentation sentinels. Helm
rejects those values, placeholder identities and versions, so the file cannot be
installed until the operator supplies independently verified API image, KServe
image and model lineage values.

## Verification and K9s

```bash
k9s --context kind-cogniflow-kserve --namespace cognitive-load-kserve
kubectl --context kind-cogniflow-kserve -n cognitive-load-kserve \
  describe inferenceservice cognitive-load-classifier
kubectl --context kind-cogniflow-kserve -n cognitive-load-kserve \
  logs deployment/cognitive-load-classifier-predictor
```

Acceptance after approval includes a Ready `InferenceService`, direct LOW/MEDIUM/HIGH
predictions and matching provenance through the public API. It also includes corrupt
or missing artifact rejection, backend failure without fallback, pod restart recovery,
exact image/model digests, conditions, logs and resource inventory. None of those
model-runtime outcomes may be inferred from successful manifest rendering.

## Rollback and scoped cleanup

```bash
helm --kube-context kind-cogniflow-kserve uninstall cognitive-load-kserve \
  --namespace cognitive-load-kserve
kubectl --context kind-cogniflow-kserve delete namespace cognitive-load-kserve
kind delete cluster --name cogniflow-kserve
```

Run cleanup only against the disposable context after exporting evidence. It
must not touch `cogniflow-local`, Terraform state, PersonalOS or Docker volumes.
Cloud migration additionally requires private networking, managed identity and
secrets, policy enforcement, signed-image admission, TLS, audit logging and an
authorized GKE cost/budget decision.
