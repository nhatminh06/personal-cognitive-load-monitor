#!/usr/bin/env bash
set -euo pipefail

output=${1:?usage: capture_module1_runtime.sh OUTPUT MODEL_NAME [NAMESPACE]}
model=${2:--}
namespace=${3:-cogniflow}

controllers=(
  kserve/kserve-controller-manager
  kserve/kserve-localmodel-controller-manager
  kserve/llmisvc-controller-manager
  kserve/kserve-kernelcachenode-agent
  knative-serving/controller
  knative-serving/autoscaler
  knative-serving/activator
  knative-serving/webhook
  knative-serving/net-istio-controller
  knative-serving/net-istio-webhook
  istio-system/istiod
  istio-system/istio-ingressgateway
  kube-system/istio-cni-node
  cert-manager/cert-manager
  cert-manager/cert-manager-webhook
  cert-manager/cert-manager-cainjector
)

controller_json='{}'
for identity in "${controllers[@]}"; do
  controller_namespace=${identity%/*}
  deployment=${identity#*/}
  workload=deployment
  [[ "$deployment" == "istio-cni-node" || "$deployment" == "kserve-kernelcachenode-agent" ]] && workload=daemonset
  selector=$(kubectl get "$workload" "$deployment" -n "$controller_namespace" -o json |
    jq -r '.spec.selector.matchLabels | to_entries | map("\(.key)=\(.value)") | join(",")')
  image=$(kubectl get pods -n "$controller_namespace" -l "$selector" -o json |
    jq -er '[.items[] | select(.status.phase == "Running") | .status.containerStatuses[]?.imageID |
      sub("^[^:]+://"; "") | select(test("@sha256:[a-f0-9]{64}$"))] | unique | if length == 1 then .[0] else error("ambiguous image inventory") end')
  available=$(kubectl get "$workload" "$deployment" -n "$controller_namespace" -o json |
    jq -er 'if .kind == "DaemonSet" then (.status.numberAvailable // 0) == (.status.desiredNumberScheduled // -1) else (.status.availableReplicas // 0) >= (.spec.replicas // 1) end')
  controller_json=$(jq -cn --argjson current "$controller_json" --arg key "$identity" --arg image "$image" \
    --argjson available "$available" '$current + {($key): {available: $available, image: $image}}')
done

crds=$(kubectl get crd -o json | jq -c '[.items[].metadata.name | select(
  test("(cert-manager\\.io|serving\\.(kserve\\.io|knative\\.dev)|internal\\.knative\\.dev|llm-d\\.ai|inference\\.networking\\.(k8s\\.io|x-k8s\\.io))$"))] | sort')
provenance=$(kubectl get configmap cogniflow-serving-inventory -n kserve -o json)
origin=""
revision_annotations='null'
if [[ "$model" != "-" ]]; then
  origin="http://${model}-predictor.${namespace}.svc.cluster.local"
  revision_annotations=$(revision=$(kubectl get configuration "${model}-predictor" -n "$namespace" -o jsonpath='{.status.latestReadyRevisionName}'); kubectl get revision "$revision" -n "$namespace" -o json | jq -c '.metadata.annotations | {"autoscaling.knative.dev/class": .["autoscaling.knative.dev/class"], "autoscaling.knative.dev/min-scale": .["autoscaling.knative.dev/min-scale"], "autoscaling.knative.dev/max-scale": .["autoscaling.knative.dev/max-scale"], "autoscaling.knative.dev/target": .["autoscaling.knative.dev/target"]}')
fi

jq -n \
  --arg kserve "$(kubectl get deployment kserve-controller-manager -n kserve -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version}' | sed 's/^v//')" \
  --arg knative "$(kubectl get deployment controller -n knative-serving -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version}' | sed 's/^v//')" \
  --arg kubernetes "$(kubectl version -o json | jq -r '.serverVersion.gitVersion | sub("^v"; "")')" \
  --arg networking "istio-$(kubectl get deployment istiod -n istio-system -o jsonpath='{.metadata.labels.operator\.istio\.io/version}')" \
  --arg cert_manager "$(kubectl get deployment cert-manager -n cert-manager -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version}' | sed 's/^v//')" \
  --arg namespace "$namespace" --arg model_name "$model" --arg origin "$origin" \
  --arg source_commit "$(jq -er '.data.source_commit' <<<"$provenance")" \
  --argjson crds "$crds" --argjson controllers "$controller_json" \
  --argjson charts "$(jq -er '.data.charts | fromjson' <<<"$provenance")" \
  --argjson autoscaler "$(kubectl get configmap config-autoscaler -n knative-serving -o json | jq -c '{"enable-scale-to-zero": .data["enable-scale-to-zero"], "stable-window": .data["stable-window"], "scale-to-zero-grace-period": .data["scale-to-zero-grace-period"]}')" \
  --argjson revision_annotations "$revision_annotations" \
  '{source_commit: $source_commit, kserve: $kserve, knative_serving: $knative, kubernetes: $kubernetes, networking: $networking,
    cert_manager: $cert_manager, namespace: $namespace, model_name: $model_name, crds: $crds,
    controllers: $controllers, charts: $charts, autoscaler: $autoscaler}
   + (if $model_name != "-" then {model_name: $model_name,
      revision_annotations: $revision_annotations,
      routes: {origin: $origin, predict: ($origin + "/v1/models/" + $model_name + ":predict"), metadata: ($origin + "/v1/models/" + $model_name + "/metadata")},
      timeouts: {api_seconds: 30, ingress_seconds: 35, revision_seconds: 35, response_start_seconds: 35, idle_seconds: 35}} else {} end)' >"$output"
