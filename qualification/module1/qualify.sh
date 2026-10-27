#!/usr/bin/env bash
set -euo pipefail

image=${KSERVE_IMAGE:?set KSERVE_IMAGE to the locally built qualification image@sha256 digest}
evidence=${EVIDENCE_DIR:-qualification-evidence}
model=qualification-model
namespace=cogniflow-qualification
mkdir -p "$evidence"

kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace "$namespace" pod-security.kubernetes.io/enforce=restricted --overwrite
kubectl create serviceaccount qualification-model -n "$namespace" --dry-run=client -o yaml | kubectl apply -f -
cat <<EOF | kubectl apply -f -
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: $model
  namespace: $namespace
  annotations:
    serving.kserve.io/deploymentMode: Knative
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
    volumes: [{name: tmp, emptyDir: {}}]
EOF

kubectl wait --for=condition=Ready "inferenceservice/$model" -n "$namespace" --timeout=600s
origin="http://${model}-predictor.${namespace}.svc.cluster.local"
request='{"instances":[[150,10,0,96,0.9375,0.0625]]}'
kubectl run qualification-client -n "$namespace" --restart=Never --image=curlimages/curl:8.16.0 --command -- sleep 3600
kubectl wait --for=condition=Ready pod/qualification-client -n "$namespace" --timeout=120s
kubectl exec -n "$namespace" qualification-client -- curl --fail --silent --show-error \
  -H 'Content-Type: application/json' -d "$request" "$origin/v1/models/$model:predict" >"$evidence/prediction.json"
kubectl exec -n "$namespace" qualification-client -- curl --fail --silent --show-error \
  "$origin/v1/models/$model/metadata" >"$evidence/metadata.json"
jq -e '.predictions | length == 1' "$evidence/prediction.json"
jq -e '.model_name == "qualification-model" and .registered_source == "local://disposable-qualification"' "$evidence/metadata.json"

kubectl delete pod qualification-client -n "$namespace" --wait=true
for _ in $(seq 1 150); do
  replicas=$(kubectl get deployment -n "$namespace" -l "serving.kserve.io/inferenceservice=$model" -o json | jq '[.items[].status.replicas // 0] | add // 0')
  [[ "$replicas" == 0 ]] && break
  sleep 2
done
[[ "${replicas:-1}" == 0 ]]
start=$(date +%s)
kubectl run qualification-client -n "$namespace" --restart=Never --image=curlimages/curl:8.16.0 --command -- sleep 3600
kubectl wait --for=condition=Ready pod/qualification-client -n "$namespace" --timeout=120s
kubectl exec -n "$namespace" qualification-client -- curl --fail --silent --show-error --retry 30 --retry-delay 2 --retry-all-errors \
  -H 'Content-Type: application/json' -d "$request" "$origin/v1/models/$model:predict" >"$evidence/cold-prediction.json"
jq -e '.predictions | length == 1' "$evidence/cold-prediction.json"
jq -n --argjson idle "$replicas" --argjson seconds "$(( $(date +%s) - start ))" '{idle_replicas:$idle,cold_activation_seconds:$seconds,prediction_succeeded:true}' >"$evidence/scale-to-zero.json"
scripts/capture_module1_runtime.sh "$evidence/runtime-snapshot.json" "$model" "$namespace"
kubectl get isvc,ksvc,configuration,revision,route,pod -n "$namespace" -o json >"$evidence/resources.json"
kubectl auth can-i --list --as=system:serviceaccount:"$namespace":qualification-model -n "$namespace" >"$evidence/service-account-permissions.txt"
echo "Evidence captured; do not mark QUALIFIED until independent human review accepts it."
