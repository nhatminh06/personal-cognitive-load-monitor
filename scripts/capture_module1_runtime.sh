#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--execute" ]] || { echo "runtime capture requires explicit --execute authorization" >&2; exit 2; }
shift
context= output= model=- namespace=cogniflow installation= rendered_dir=
while (($#)); do
  case "$1" in
    --context) context=${2:?}; shift 2 ;;
    --output) output=${2:?}; shift 2 ;;
    --model) model=${2:?}; shift 2 ;;
    --namespace) namespace=${2:?}; shift 2 ;;
    --installation) installation=${2:?}; shift 2 ;;
    --rendered-dir) rendered_dir=${2:?}; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$context" && -n "$output" ]] || { echo "--context and --output are required" >&2; exit 2; }
[[ "$(kubectl config current-context)" == "$context" ]] || { echo "current context mismatch" >&2; exit 1; }
k=(kubectl --context "$context")

controllers=(
  kserve/kserve-controller-manager kserve/kserve-localmodel-controller-manager
  kserve/llmisvc-controller-manager
  knative-serving/controller knative-serving/autoscaler knative-serving/activator
  knative-serving/webhook knative-serving/net-istio-controller knative-serving/net-istio-webhook
  istio-system/istiod istio-system/istio-ingressgateway kube-system/istio-cni-node
  cert-manager/cert-manager cert-manager/cert-manager-webhook cert-manager/cert-manager-cainjector
)

controller_json='{}'
for identity in "${controllers[@]}"; do
  controller_namespace=${identity%/*}
  workload_name=${identity#*/}
  workload=deployment
  [[ "$workload_name" == "istio-cni-node" ]] && workload=daemonset
  workload_json=$("${k[@]}" get "$workload" "$workload_name" -n "$controller_namespace" -o json)
  selector=$(jq -er '.spec.selector.matchLabels | to_entries | map("\(.key)=\(.value)") | join(",") | select(length > 0)' <<<"$workload_json")
  images=$("${k[@]}" get pods -n "$controller_namespace" -l "$selector" -o json | jq -cer '
    [.items[] | select(.status.phase == "Running") | .status.containerStatuses[]?.imageID |
    sub("^[^:]+://"; "") | select(test("@sha256:[a-f0-9]{64}$"))] | unique |
    if length > 0 then . else error("missing imageID digest") end')
  available=$(jq -er 'if .kind == "DaemonSet" then
    (.status.numberAvailable // 0) > 0 and (.status.numberAvailable == .status.desiredNumberScheduled)
    else (.status.availableReplicas // 0) > 0 and (.status.availableReplicas >= (.spec.replicas // 1)) end' <<<"$workload_json")
  controller_json=$(jq -cn --argjson current "$controller_json" --arg key "$identity" \
    --arg kind "$workload" --argjson images "$images" --argjson available "$available" \
    '$current + {($key): {kind: $kind, available: $available, images: $images}}')
done

crds=$("${k[@]}" get crd -o json | jq -cer '[.items[] | select(.metadata.name |
  test("(cert-manager\\.io|serving\\.(kserve\\.io|knative\\.dev)|internal\\.knative\\.dev|llm-d\\.ai|inference\\.networking\\.(k8s\\.io|x-k8s\\.io))$")) |
  if any(.status.conditions[]?; .type == "Established" and .status == "True") then .metadata.name
  else error("required CRD is not Established") end] | sort')

installation_json='null'
if [[ -n "$installation" || -n "$rendered_dir" ]]; then
  [[ -f "$installation" && -d "$rendered_dir" ]] || { echo "installation evidence is incomplete" >&2; exit 1; }
  installation_json=$(jq -cer 'if .method == "kustomize" and (.source_commit | test("^[a-f0-9]{40}$")) then . else error("invalid installation evidence") end' "$installation")
  while IFS=$'\t' read -r component expected; do
    actual=$(sha256sum "$rendered_dir/$component.yaml" | cut -d' ' -f1)
    [[ "$actual" == "$expected" ]] || { echo "rendered manifest hash mismatch: $component" >&2; exit 1; }
  done < <(jq -r '.rendered_manifests | to_entries[] | [.key,.value] | @tsv' "$installation")
  while IFS='|' read -r api_version kind resource_namespace name; do
    resource=$kind
    [[ "$api_version" == */* ]] && resource="$kind.${api_version%/*}"
    resource_args=(get "$resource" "$name" -o name)
    [[ -n "$resource_namespace" ]] && resource_args+=(-n "$resource_namespace")
    "${k[@]}" "${resource_args[@]}" >/dev/null
  done < <(jq -r '.resource_identities[] | [.apiVersion,.kind,.namespace,.name] | join("|")' "$installation")
  declared_commit=$("${k[@]}" get configmap cogniflow-serving-inventory -n kserve -o jsonpath='{.data.source_commit}')
  [[ "$declared_commit" == "$(jq -r .source_commit "$installation")" ]] || { echo "source provenance is contradictory" >&2; exit 1; }
fi

configuration=$(jq -cn \
  --argjson autoscaler "$("${k[@]}" get configmap config-autoscaler -n knative-serving -o json | jq -c '{"enable-scale-to-zero": .data["enable-scale-to-zero"], "stable-window": .data["stable-window"], "scale-to-zero-grace-period": .data["scale-to-zero-grace-period"]}')" \
  --argjson defaults "$("${k[@]}" get configmap config-defaults -n knative-serving -o json | jq -c '{"revision-timeout-seconds": .data["revision-timeout-seconds"], "revision-response-start-timeout-seconds": .data["revision-response-start-timeout-seconds"], "revision-idle-timeout-seconds": .data["revision-idle-timeout-seconds"]}')" \
  '{autoscaler:$autoscaler, defaults:$defaults}')

kserve=$("${k[@]}" get crd inferenceservices.serving.kserve.io \
  -o jsonpath='{.metadata.annotations.controller-gen\.kubebuilder\.io/version}' | sed 's/^v//')
knative=$("${k[@]}" get deployment controller -n knative-serving \
  -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version}' | sed 's/^v//')
kubernetes=$("${k[@]}" version -o json | jq -er '.serverVersion.gitVersion | sub("^v"; "")')
istio=$("${k[@]}" get deployment istiod -n istio-system \
  -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version}')
cert_manager=$("${k[@]}" get deployment cert-manager -n cert-manager \
  -o jsonpath='{.metadata.labels.app\.kubernetes\.io/version}' | sed 's/^v//')
[[ "$kserve" == 0.21.0 && "$knative" == 1.23.0 && "$kubernetes" == 1.34.11 \
  && "$istio" == 1.31.3 && "$cert_manager" == 1.21.2 ]] || {
  echo "live serving versions do not match the pinned qualification stack" >&2
  exit 1
}

origin= revision_annotations=null
if [[ "$model" != "-" ]]; then
  origin="http://${model}-predictor.${namespace}.svc.cluster.local"
  revision=$("${k[@]}" get configuration "${model}-predictor" -n "$namespace" -o jsonpath='{.status.latestReadyRevisionName}')
  [[ -n "$revision" ]] || { echo "ready revision is missing" >&2; exit 1; }
  revision_annotations=$("${k[@]}" get revision "$revision" -n "$namespace" -o json | jq -c '.metadata.annotations | {"autoscaling.knative.dev/class": .["autoscaling.knative.dev/class"], "autoscaling.knative.dev/min-scale": .["autoscaling.knative.dev/min-scale"], "autoscaling.knative.dev/max-scale": .["autoscaling.knative.dev/max-scale"], "autoscaling.knative.dev/target": .["autoscaling.knative.dev/target"]}')
fi

jq -n \
  --arg kserve "$kserve" --arg knative "$knative" --arg kubernetes "$kubernetes" \
  --arg networking "istio-$istio" --arg cert_manager "$cert_manager" \
  --arg namespace "$namespace" --arg model_name "$model" --arg origin "$origin" \
  --argjson crds "$crds" --argjson controllers "$controller_json" \
  --argjson configuration "$configuration" --argjson installation "$installation_json" \
  --argjson revision_annotations "$revision_annotations" \
  '{kserve:$kserve, knative_serving:$knative, kubernetes:$kubernetes, networking:$networking,
    cert_manager:$cert_manager, namespace:$namespace, crds:$crds, controllers:$controllers,
    configuration:$configuration}
   + (if $installation != null then {installation:$installation} else {} end)
   + (if $model_name != "-" then {model_name:$model_name, revision_annotations:$revision_annotations,
      routes:{origin:$origin, predict:($origin + "/v1/models/" + $model_name + ":predict"),
      metadata:($origin + "/v1/models/" + $model_name + "/metadata")}} else {} end)' >"$output"
