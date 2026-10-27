#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--execute" && $# == 3 && "$2" == "--evidence-dir" ]] || {
  echo "usage: qualify.sh --execute --evidence-dir INSTALL_EVIDENCE_DIRECTORY" >&2
  exit 2
}
image=${KSERVE_IMAGE:?set KSERVE_IMAGE to the locally built qualification image@sha256 digest}
[[ "$image" =~ @sha256:[a-f0-9]{64}$ ]] || { echo "KSERVE_IMAGE must be immutable" >&2; exit 1; }
evidence=$3
[[ -f "$evidence/installation.json" && -d "$evidence/rendered" ]] || { echo "installation evidence is missing" >&2; exit 1; }
[[ -f "$evidence/kubeconfig" ]] || { echo "dedicated qualification kubeconfig is missing" >&2; exit 1; }
export KUBECONFIG="$evidence/kubeconfig"
context=kind-cogniflow-module1-qualification
model=qualification-model
namespace=cogniflow-qualification
deadline=35
k=(kubectl --context "$context")
[[ "$(kubectl config current-context)" == "$context" ]] || { echo "current context mismatch" >&2; exit 1; }
exec > >(tee "$evidence/qualification.log") 2>&1

observations=$evidence/scale-observations.jsonl
result=$evidence/qualification-result.json
: >"$observations"
record() {
  jq -cn --arg timestamp "$(date --iso-8601=ns)" --arg state "$1" --argjson ready "$2" \
    '{timestamp:$timestamp,state:$state,ready_replicas:$ready}' >>"$observations"
}
failed() {
  jq -n --arg timestamp "$(date --iso-8601=ns)" '{status:"FAIL",finished_at:$timestamp}' >"$result"
}
trap failed ERR

"${k[@]}" create namespace "$namespace" --dry-run=client -o yaml | "${k[@]}" apply -f -
"${k[@]}" label namespace "$namespace" pod-security.kubernetes.io/enforce=restricted --overwrite
"${k[@]}" apply --dry-run=server -f qualification/module1/qualification-client.yaml >/dev/null
"${k[@]}" create serviceaccount qualification-model -n "$namespace" --dry-run=client -o yaml | "${k[@]}" apply -f -
cat <<EOF | "${k[@]}" apply -f -
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: $model
  namespace: $namespace
  annotations:
    serving.kserve.io/deploymentMode: Knative
    networking.knative.dev/visibility: cluster-local
    autoscaling.knative.dev/class: kpa.autoscaling.knative.dev
    autoscaling.knative.dev/min-scale: "0"
    autoscaling.knative.dev/max-scale: "3"
    autoscaling.knative.dev/target: "1"
spec:
  predictor:
    serviceAccountName: qualification-model
    containers:
    - name: kserve-container
      image: $image
      args: ["--model_name", "$model", "--http_port", "8080", "--enable_grpc=false"]
      securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, runAsNonRoot: true, runAsUser: 10001, seccompProfile: {type: RuntimeDefault}, capabilities: {drop: ["ALL"]}}
      resources: {requests: {cpu: 100m, memory: 256Mi}, limits: {cpu: 500m, memory: 512Mi}}
      volumeMounts: [{name: tmp, mountPath: /tmp}]
    volumes: [{name: tmp, emptyDir: {sizeLimit: 64Mi}}]
EOF

"${k[@]}" wait --for=condition=Ready "inferenceservice/$model" -n "$namespace" --timeout=600s
selector="serving.kserve.io/inferenceservice=$model"
ready=$("${k[@]}" get deployment -n "$namespace" -l "$selector" -o json | jq '[.items[].status.readyReplicas // 0] | add // 0')
((ready >= 1)) || { echo "predictor never reached a Ready replica" >&2; exit 1; }
record READY "$ready"

"${k[@]}" apply -f qualification/module1/qualification-client.yaml
"${k[@]}" wait --for=condition=Ready pod/qualification-client -n "$namespace" --timeout=120s
origin="http://${model}-predictor.${namespace}.svc.cluster.local"
request='{"instances":[[150,10,0,96,0.9375,0.0625]]}'
predict() {
  timeout "$((deadline + 5))s" "${k[@]}" exec -n "$namespace" qualification-client -- \
    curl --silent --show-error --connect-timeout 3 --max-time "$deadline" \
    -H 'Content-Type: application/json' -d "$request" -w $'\n%{http_code}' \
    "$origin/v1/models/$model:predict"
}
response=$(predict)
[[ "$(tail -n1 <<<"$response")" == 200 ]] || { echo "initial inference did not return HTTP 200" >&2; exit 1; }
head -n -1 <<<"$response" >"$evidence/prediction.json"
jq -e '.predictions == ["LOW"] and .provenance.model_name == "qualification-model"' "$evidence/prediction.json" >/dev/null
record INITIAL_INFERENCE "$ready"
"${k[@]}" exec -n "$namespace" qualification-client -- \
  curl --fail --silent --show-error --connect-timeout 3 --max-time 10 \
  "$origin/v1/models/$model/metadata" >"$evidence/metadata.json"
jq -e '.model_name == "qualification-model" and .registered_source == "local://disposable-qualification"' "$evidence/metadata.json" >/dev/null

"${k[@]}" delete pod qualification-client -n "$namespace" --wait=true --timeout=60s
ready=-1
for _ in $(seq 1 150); do
  ready=$("${k[@]}" get deployment -n "$namespace" -l "$selector" -o json | jq '[.items[].status.readyReplicas // 0] | add // 0')
  [[ "$ready" == 0 ]] && break
  sleep 2
done
[[ "$ready" == 0 ]] || { echo "predictor did not scale to exactly zero" >&2; exit 1; }
record SCALED_TO_ZERO 0

"${k[@]}" apply -f qualification/module1/qualification-client.yaml
"${k[@]}" wait --for=condition=Ready pod/qualification-client -n "$namespace" --timeout=120s
start=$(date +%s)
response=$(predict)
elapsed=$(( $(date +%s) - start ))
[[ "$elapsed" -le "$deadline" && "$(tail -n1 <<<"$response")" == 200 ]] || {
  echo "cold activation exceeded ${deadline}s or failed" >&2
  exit 1
}
head -n -1 <<<"$response" >"$evidence/cold-prediction.json"
jq -e '.predictions == ["LOW"] and .provenance.model_name == "qualification-model"' "$evidence/cold-prediction.json" >/dev/null
ready=$("${k[@]}" get deployment -n "$namespace" -l "$selector" -o json | jq '[.items[].status.readyReplicas // 0] | add // 0')
((ready >= 1)) || { echo "predictor did not return to a Ready replica" >&2; exit 1; }
record COLD_ACTIVATION_READY "$ready"
record POST_ACTIVATION_INFERENCE "$ready"

jq -n --arg timestamp "$(date --iso-8601=ns)" --argjson seconds "$elapsed" \
  --argjson deadline "$deadline" --slurpfile observations "$observations" \
  '{status:"PASS",finished_at:$timestamp,cold_activation_seconds:$seconds,
  cold_activation_deadline_seconds:$deadline,states:[$observations[].state]}' >"$result"
scripts/capture_module1_runtime.sh --execute --context "$context" \
  --output "$evidence/runtime-snapshot.json" --model "$model" --namespace "$namespace" \
  --installation "$evidence/installation.json" --rendered-dir "$evidence/rendered"
jq --slurpfile acceptance "$result" '. + {acceptance:$acceptance[0]}' \
  "$evidence/runtime-snapshot.json" >"$evidence/runtime-snapshot.tmp"
mv "$evidence/runtime-snapshot.tmp" "$evidence/runtime-snapshot.json"
"${k[@]}" get isvc,ksvc,configuration,revision,route,pod -n "$namespace" -o json >"$evidence/resources.json"
"${k[@]}" auth can-i --list --as=system:serviceaccount:"$namespace":qualification-model \
  -n "$namespace" >"$evidence/service-account-permissions.txt"
trap - ERR
echo "Evidence captured; only independent human review may change the BLOCKED matrix."
