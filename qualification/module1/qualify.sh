#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--execute" && $# == 5 && "$2" == "--installation-evidence" \
  && "$4" == "--qualification-evidence" ]] || {
  echo "usage: qualify.sh --execute --installation-evidence INSTALL_DIRECTORY --qualification-evidence NEW_DIRECTORY" >&2
  exit 2
}
installation=$3
evidence=$5
[[ -f "$installation/installation.json" && -d "$installation/rendered" ]] || { echo "installation evidence is missing" >&2; exit 1; }
[[ -f "$installation/kubeconfig" ]] || { echo "dedicated qualification kubeconfig is missing" >&2; exit 1; }
[[ "$evidence" == /* && "$evidence" != "$(pwd)"/* && ! -e "$evidence" ]] || {
  echo "qualification evidence must be a new absolute directory outside the repository" >&2
  exit 1
}
mkdir -m 0700 "$evidence"
export KUBECONFIG="$installation/kubeconfig"
context=kind-cogniflow-module1-qualification
cluster=cogniflow-module1-qualification
model=qualification-model
namespace=cogniflow-qualification
deadline=35
k=(kubectl --context "$context")
exec > >(tee "$evidence/qualification.log") 2>&1

observations=$evidence/scale-observations.jsonl
result=$evidence/qualification-result.json
: >"$observations"
context_verified=false
record() {
  jq -cn --arg timestamp "$(date --iso-8601=ns)" --arg state "$1" --argjson ready "$2" \
    '{timestamp:$timestamp,state:$state,ready_replicas:$ready}' >>"$observations"
}
failed() {
  trap - ERR
  jq -n --arg timestamp "$(date --iso-8601=ns)" '{status:"FAIL",finished_at:$timestamp}' >"$result"
  if [[ "$context_verified" == true ]]; then
    timeout 15s "${k[@]}" get isvc,ksvc,revision,deployment,pod -n "$namespace" -o json \
      >"$evidence/failure-resources.json" 2>"$evidence/failure-resources.stderr" || true
    timeout 15s "${k[@]}" get events -n "$namespace" -o json \
      >"$evidence/failure-events.json" 2>"$evidence/failure-events.stderr" || true
  fi
}
abort() {
  echo "$1" >&2
  failed
  trap - ERR
  exit 1
}
trap failed ERR

image=${KSERVE_IMAGE:-}
[[ "$image" =~ @sha256:[a-f0-9]{64}$ ]] || abort "KSERVE_IMAGE must be an immutable local image digest"
[[ "$(kubectl config current-context)" == "$context" ]] || abort "current context mismatch"
[[ "$(kind get clusters | grep -Fx "$cluster")" == "$cluster" ]] || abort "exact disposable cluster is missing"
context_verified=true
"${k[@]}" version -o json >"$evidence/kubectl-version.json"
jq -e '
  [.clientVersion.minor, .serverVersion.minor] |
  map(capture("^(?<minor>[0-9]+)").minor | tonumber) |
  ((.[0] - .[1]) | if . < 0 then -. else . end) <= 1
' "$evidence/kubectl-version.json" >/dev/null || abort "kubectl client/server minor skew exceeds one version"
docker exec "$cluster-control-plane" crictl inspecti "$image" >"$evidence/qualification-image-resolution.json"
sha256sum "$installation/installation.json" "$installation/rendered-manifests.sha256" \
  >"$evidence/installation-evidence.sha256"
package=${QUALIFICATION_MODEL_PACKAGE:-build/model-package}
PYTHONPATH=src UV_CACHE_DIR=/tmp/cogniflow-qualification-uv \
  uv run --offline --frozen python scripts/module1_qualification_model.py --package "$package" \
  --output "$evidence/model-runtime-environment.json"
sha256sum "$package/cognitive_load_model.skops" "$package/model-package.json" \
  >"$evidence/model-package.sha256"
model_sha=$(jq -er .MODEL_SHA256 "$evidence/model-runtime-environment.json")
artifact_sha=$(jq -er .MODEL_ARTIFACT_SHA256 "$evidence/model-runtime-environment.json")
dataset_sha=$(jq -er .MODEL_DATASET_SHA256 "$evidence/model-runtime-environment.json")

"${k[@]}" create namespace "$namespace" --dry-run=client -o yaml | "${k[@]}" apply -f -
"${k[@]}" label namespace "$namespace" pod-security.kubernetes.io/enforce=restricted --overwrite
"${k[@]}" delete pod qualification-client -n "$namespace" --ignore-not-found --wait=true --timeout=60s
python scripts/module1_qualification_client.py --execute --context "$context" \
  --service-account qualification/module1/qualification-client-serviceaccount.yaml \
  --pod qualification/module1/qualification-client.yaml
"${k[@]}" apply --dry-run=server \
  -f qualification/module1/qualification-client-gateway-policy.yaml >/dev/null
"${k[@]}" apply -f qualification/module1/qualification-client-gateway-policy.yaml
"${k[@]}" get networkpolicy allow-qualification-client-to-cluster-local-gateway \
  -n istio-system -o json >"$evidence/qualification-gateway-policy.json"
"${k[@]}" create serviceaccount qualification-model -n "$namespace" --dry-run=client -o yaml | "${k[@]}" apply -f -
cat <<EOF >"$evidence/inferenceservice.yaml"
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: $model
  namespace: $namespace
  labels:
    networking.kserve.io/visibility: cluster-local
    networking.knative.dev/visibility: cluster-local
  annotations:
    serving.kserve.io/deploymentMode: Knative
    autoscaling.knative.dev/class: kpa.autoscaling.knative.dev
    autoscaling.knative.dev/min-scale: "0"
    autoscaling.knative.dev/max-scale: "3"
    autoscaling.knative.dev/target: "1"
spec:
  predictor:
    minReplicas: 0
    maxReplicas: 3
    scaleTarget: 1
    serviceAccountName: qualification-model
    containers:
    - name: kserve-container
      image: $image
      args: ["--model_name", "$model", "--http_port", "8080", "--enable_grpc=false"]
      env:
      - {name: MODEL_NAME, value: qualification-model}
      - {name: MODEL_VERSION, value: "1"}
      - {name: MODEL_ARTIFACT_SHA256, value: "$artifact_sha"}
      - {name: MODEL_DATASET_SHA256, value: "$dataset_sha"}
      - {name: MODEL_FEATURE_SCHEMA_VERSION, value: "1.0"}
      - {name: MODEL_SHA256, value: "$model_sha"}
      securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, runAsNonRoot: true, runAsUser: 10001, seccompProfile: {type: RuntimeDefault}, capabilities: {drop: ["ALL"]}}
      resources: {requests: {cpu: 100m, memory: 256Mi}, limits: {cpu: 500m, memory: 512Mi}}
      volumeMounts: [{name: tmp, mountPath: /tmp}]
    volumes: [{name: tmp, emptyDir: {sizeLimit: 64Mi}}]
EOF
"${k[@]}" apply --dry-run=server -f "$evidence/inferenceservice.yaml" >/dev/null
"${k[@]}" apply -f "$evidence/inferenceservice.yaml"

"${k[@]}" wait --for=condition=Ready "inferenceservice/$model" -n "$namespace" --timeout=600s
"${k[@]}" get kservice "$model-predictor" -n "$namespace" -o json \
  >"$evidence/knative-service.json"
jq -e '
  .metadata.labels["networking.kserve.io/visibility"] == "cluster-local" and
  .metadata.labels["networking.knative.dev/visibility"] == "cluster-local" and
  (.spec.template.metadata.annotations["networking.kserve.io/visibility"] == null) and
  (.spec.template.metadata.annotations["networking.knative.dev/visibility"] == null) and
  (.status.url | endswith(".svc.cluster.local"))
' "$evidence/knative-service.json" >/dev/null || abort "Knative Service is not strictly cluster-local"
jq -e '
  .spec.template.metadata.annotations as $a |
  $a["autoscaling.knative.dev/class"] == "kpa.autoscaling.knative.dev" and
  $a["autoscaling.knative.dev/min-scale"] == "0" and
  $a["autoscaling.knative.dev/max-scale"] == "3" and
  $a["autoscaling.knative.dev/target"] == "1"
' "$evidence/knative-service.json" >/dev/null || abort "effective Knative autoscaling must be KPA min=0 max=3 target=1"
revision=$(jq -er '.status.latestReadyRevisionName' "$evidence/knative-service.json")
jq -e --arg revision "$revision" '
  .status.latestCreatedRevisionName == $revision and
  (.status.traffic | length == 1) and
  .status.traffic[0].revisionName == $revision and .status.traffic[0].percent == 100
' "$evidence/knative-service.json" >/dev/null || abort "traffic must target the current Ready revision exclusively"
selector="serving.knative.dev/revision=$revision"

wait_ready() {
  local phase=$1
  while true; do
    elapsed=$(( $(date +%s) - start ))
    remaining=$((deadline - elapsed))
    ((remaining > 0)) || abort "$phase readiness exceeded the original activation deadline"
    ready=$(timeout "${remaining}s" "${k[@]}" get deployment -n "$namespace" -l "$selector" -o json |
      jq -er 'if (.items | length) != 1 then error("expected one revision deployment")
      else .items[0].status.readyReplicas // 0 end')
    elapsed=$(( $(date +%s) - start ))
    jq -cn --argjson elapsed "$elapsed" --argjson ready "$ready" \
      '{elapsed_seconds:$elapsed,ready_replicas:$ready}' >>"$evidence/$phase-readiness-observations.jsonl"
    ((elapsed <= deadline)) || abort "$phase readiness exceeded the original activation deadline"
    ((ready >= 1)) && break
    sleep 1
  done
}

origin="http://${model}-predictor.${namespace}.svc.cluster.local"
request='{"instances":[[150,10,0,96,0.9375,0.0625]]}'
predict() {
  timeout "$((deadline + 5))s" "${k[@]}" exec -n "$namespace" qualification-client -- \
    curl --silent --show-error --connect-timeout 3 --max-time "$deadline" \
    -H 'Content-Type: application/json' -d "$request" -w $'\n%{http_code}' \
    "$origin/v1/models/$model:predict"
}
# Ready is compatible with zero replicas: activate an idle revision before checking replicas.
start=$(date +%s)
response=$(predict)
[[ "$(tail -n1 <<<"$response")" == 200 ]] || abort "initial inference did not return HTTP 200"
head -n -1 <<<"$response" >"$evidence/prediction.json"
jq -e '.predictions == ["LOW"] and .provenance.model_name == "qualification-model"' "$evidence/prediction.json" >/dev/null
wait_ready initial
record READY "$ready"
record INITIAL_INFERENCE "$ready"
"${k[@]}" exec -n "$namespace" qualification-client -- \
  curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  "$origin/v1/models/$model/metadata" >"$evidence/metadata.json"
jq -e '.model_name == "qualification-model" and .registered_source == "local://disposable-qualification"' "$evidence/metadata.json" >/dev/null

"${k[@]}" delete pod qualification-client -n "$namespace" --wait=true --timeout=60s
ready=-1
for _ in $(seq 1 150); do
  "${k[@]}" get deployment -n "$namespace" -l "$selector" -o json --request-timeout=10s >"$evidence/zero-deployment.json"
  "${k[@]}" get pod -n "$namespace" -l "$selector" -o json --request-timeout=10s >"$evidence/zero-pods.json"
  if jq -e '(.items | length) == 1 and (.items[0] |
    .spec.replicas == 0 and (.status.replicas // 0) == 0 and
    (.status.readyReplicas // 0) == 0 and .status.observedGeneration >= .metadata.generation)' \
    "$evidence/zero-deployment.json" >/dev/null &&
    jq -e '(.items | length) == 0' "$evidence/zero-pods.json" >/dev/null; then
    ready=0
    break
  fi
  sleep 2
done
[[ "$ready" == 0 ]] || abort "predictor did not scale to exactly zero"
record SCALED_TO_ZERO 0

"${k[@]}" apply -f qualification/module1/qualification-client.yaml
"${k[@]}" wait --for=condition=Ready pod/qualification-client -n "$namespace" --timeout=120s
start=$(date +%s)
response=$(predict)
elapsed=$(( $(date +%s) - start ))
[[ "$elapsed" -le "$deadline" && "$(tail -n1 <<<"$response")" == 200 ]] || {
  abort "cold activation exceeded ${deadline}s or failed"
}
head -n -1 <<<"$response" >"$evidence/cold-prediction.json"
jq -e '.predictions == ["LOW"] and .provenance.model_name == "qualification-model"' "$evidence/cold-prediction.json" >/dev/null
wait_ready cold
record COLD_ACTIVATION_READY "$ready"
response=$(predict)
[[ "$(tail -n1 <<<"$response")" == 200 ]] || abort "post-activation inference failed"
head -n -1 <<<"$response" >"$evidence/post-activation-prediction.json"
jq -e '.predictions == ["LOW"] and .provenance.model_name == "qualification-model"' "$evidence/post-activation-prediction.json" >/dev/null
record POST_ACTIVATION_INFERENCE "$ready"

jq -n --arg timestamp "$(date --iso-8601=ns)" --argjson seconds "$elapsed" \
  --argjson deadline "$deadline" --slurpfile observations "$observations" \
  '{status:"PASS",finished_at:$timestamp,cold_activation_seconds:$seconds,
  cold_activation_deadline_seconds:$deadline,states:[$observations[].state]}' >"$result"
scripts/capture_module1_runtime.sh --execute --context "$context" \
  --output "$evidence/runtime-snapshot.json" --model "$model" --namespace "$namespace" \
  --installation "$installation/installation.json" --rendered-dir "$installation/rendered"
jq --slurpfile acceptance "$result" '. + {acceptance:$acceptance[0]}' \
  "$evidence/runtime-snapshot.json" >"$evidence/runtime-snapshot.tmp"
mv "$evidence/runtime-snapshot.tmp" "$evidence/runtime-snapshot.json"
"${k[@]}" get isvc,ksvc,configuration,revision,route,pod -n "$namespace" -o json >"$evidence/resources.json"
"${k[@]}" auth can-i --list --as=system:serviceaccount:"$namespace":qualification-model \
  -n "$namespace" >"$evidence/service-account-permissions.txt"
trap - ERR
echo "Evidence captured; only independent human review may change the BLOCKED matrix."
