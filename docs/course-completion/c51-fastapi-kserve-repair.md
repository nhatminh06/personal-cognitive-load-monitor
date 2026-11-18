# C5.1 FastAPI/KServe source repair and runtime handoff

**Inspection date:** 2026-11-17

**Starting revision:** `dd93c2f43c702ef17d64f82c70a07f97b1788365`

**Runtime decision:** source repair is locally testable; deployment remains unauthorized.

## Read-only findings

The `cogniflow-module1-qualification` cluster was inspected through
`/tmp/cogniflow-module1-inspect.yaml`; no object was changed.

- Both FastAPI replicas were running but unready because `/ready` returned 503.
  This is intended fail-closed behavior: the configured KServe metadata request
  could not reach a healthy route and verify the exact model identity.
- `qualification-model` had a Ready predictor revision but its InferenceService
  route was `Unknown`. KServe reported `failed to get Gateway
  "kubeflow/kubeflow-gateway"`. The KServe `inferenceservice-config` selected
  that nonexistent Gateway while the cluster contained
  `istio-system/istio-ingressgateway`, `istio-system/cluster-local-gateway`, and
  `knative-serving/knative-local-gateway`.
- Knative's `config-istio` retained the same stale legacy
  `gateway.kubeflow.kubeflow-gateway` entry. This controller configuration is
  separate from the application release and requires cluster-owner action.
- The deployed InferenceService lacked both cluster-local visibility labels and
  the generated Knative Service had an external `example.com` URL. The chart
  emitted only the Knative label. It now emits the KServe and Knative labels,
  matching the already-qualified KServe 0.21 contract.
- The deployed Knative Service used `min-scale: "1"` although the release
  requested zero. KServe derives this contract from predictor fields, so the
  chart now sets `minReplicas`, `maxReplicas`, and `scaleTarget` explicitly.

The API and predictor still identify the historical qualification model. The
unapproved C2.2 candidate is not selected, approved, packaged, or deployed.

## Authorized runtime acceptance procedure

Use a disposable or explicitly authorized environment only. Set shell variables
to owner-reviewed values; never copy the examples below as model approval.

1. Require a `kubectl` minor within one of the Kubernetes server minor, the
   exact KServe 0.21/Knative Serving 1.23 controller identities, and repository
   image references pinned by registry digest. Verify each image signature,
   provenance/SBOM, and a complete current Trivy scan with zero HIGH and zero
   CRITICAL findings. M10.3 currently prevents this gate from passing.
2. Obtain explicit approval for one exact registered model version, artifact-tree
   digest, packaged-model digest, dataset digest, run ID, and feature contract.
   Candidate status is insufficient.
3. Before any release mutation, capture and validate gateway state:

   ```bash
   kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" \
     -n kserve get configmap inferenceservice-config -o json > "$EVIDENCE/kserve-config.json"
   kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" \
     get gateways.networking.istio.io -A -o json > "$EVIDENCE/gateways.json"
   python scripts/validate_kserve_gateways.py \
     --config-map "$EVIDENCE/kserve-config.json" --gateways "$EVIDENCE/gateways.json" \
     --expected-ingress istio-system/istio-ingressgateway \
     --expected-local knative-serving/knative-local-gateway
   ```

   On the inspected cluster this fails until an owner changes the KServe ingress
   gateway from `kubeflow/kubeflow-gateway` to the existing, explicitly reviewed
   gateway and removes the stale Knative legacy reference. Do not create a
   look-alike Gateway merely to satisfy the name.
4. Confirm the target namespace has restricted Pod Security admission, the
   dedicated service accounts and API-key Secret exist, and NetworkPolicies
   admit only the API-to-predictor path plus the reviewed Knative local gateway.
   Server-side dry-run the rendered release and independently verify both image
   digests and every model identity value before an authorized Helm upgrade.

   ```bash
   helm template module1 helm/cognitive-load-monitor --namespace "$NAMESPACE" \
     -f helm/cognitive-load-monitor/values.gke.yaml \
     -f helm/cognitive-load-monitor/values.module1-knative.yaml \
     --set-string kserve.name="$MODEL_NAME" \
     --set-string config.modelName="$MODEL_NAME" \
     --set-string config.modelVersion="$MODEL_VERSION" \
     --set image.repository="$API_REPOSITORY" --set image.digest="$API_DIGEST" \
     --set kserve.image.repository="$KSERVE_REPOSITORY" \
     --set kserve.image.digest="$KSERVE_DIGEST" \
     --set config.modelSha256="$MODEL_SHA256" \
     --set config.modelArtifactSha256="$ARTIFACT_SHA256" \
     --set config.modelDatasetSha256="$DATASET_SHA256" > "$EVIDENCE/release.yaml"
   kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" \
     apply --dry-run=server -f "$EVIDENCE/release.yaml"
   helm --kubeconfig "$KUBECONFIG" --kube-context "$CONTEXT" upgrade --install module1 \
     helm/cognitive-load-monitor --namespace "$NAMESPACE" --create-namespace \
     --values "$OWNER_REVIEWED_VALUES"
   ```
5. Wait for `InferenceService/Ready=True`, require its generated Knative Service
   to carry both cluster-local labels and a `.svc.cluster.local` address, and
   require effective KPA min/max/target `0/3/1`. Capture conditions, events,
   Services, Routes, image IDs, policies, and logs.
6. From a restricted in-cluster client, request predictor metadata and one direct
   prediction; compare every returned provenance field and output to the approved
   record. Then call authenticated FastAPI `/ready`, `/model-info`, and `/predict`.
   Prove wrong API keys, backend outage, model-identity mismatch, corrupt package,
   and failed reload all fail closed with no rule/local fallback.
7. Restart one predictor pod, wait for readiness recovery, and repeat direct and
   FastAPI predictions. Preserve timestamps and recovery duration.
8. Roll back only the authorized Helm release to its previously recorded revision,
   wait for the previous digest identities and readiness, and capture post-rollback
   conditions. Do not delete shared controllers, namespaces, or clusters.

Knative Eventing remains disabled. M10.3 deployment NO-GO and SEC-022 are
unchanged; neither is bypassed by this source repair.

## Local validation

- Focused FastAPI, KServe client/server/manifest, and gateway tests: 119 passed.
- Full Python regression: 630 passed, 2 skipped, 5 warnings; 87.20% coverage
  across the nine configured packages plus focus, above the 81% gate.
- Ruff passed; scoped MyPy passed for 23 source files.
- Helm lint passed (informational icon recommendation only); the Module I
  Knative render passed and produced both visibility labels plus `0/3/1`.
- The first sandboxed full-suite attempt could not create its loopback tracing
  server. The unchanged suite passed with authorized local loopback access.
