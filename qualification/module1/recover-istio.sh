#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--execute" && "${2:-}" == "--original-evidence" && -n "${3:-}" \
  && "${4:-}" == "--recovery-evidence" && -n "${5:-}" && $# == 5 ]] || {
  echo "usage: recover-istio.sh --execute --original-evidence PARTIAL_EVIDENCE --recovery-evidence NEW_DIRECTORY" >&2
  exit 2
}

commit=f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0
cluster=cogniflow-module1-qualification
context=kind-cogniflow-module1-qualification
original=$3
recovery=$5
for path in "$original" "$recovery"; do
  [[ "$path" == /* && "$path" != "$(pwd)"/* ]] || {
    echo "evidence directories must be absolute paths outside the repository" >&2
    exit 1
  }
done
[[ -d "$original" && -f "$original/kubeconfig" && -d "$original/upstream" \
  && -d "$original/raw-rendered" && -d "$original/rendered" ]] || {
  echo "original partial-install evidence is incomplete" >&2
  exit 1
}
[[ ! -e "$recovery" ]] || { echo "recovery evidence directory already exists" >&2; exit 1; }
[[ "$(git -C "$original/upstream" rev-parse HEAD)" == "$commit" ]] || {
  echo "partial installation used an unexpected upstream commit" >&2
  exit 1
}
sha256sum --check "$original/rendered-manifests.sha256"

mkdir -m 0700 "$recovery"
exec > >(tee "$recovery/recovery.log") 2>&1
failed() { jq -n --arg timestamp "$(date --iso-8601=ns)" '{status:"FAIL",finished_at:$timestamp}' >"$recovery/recovery-result.json"; }
trap failed ERR

find "$original" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum \
  >"$recovery/original-evidence.sha256"
mkdir -m 0700 "$recovery/raw-rendered"
cp "$original"/raw-rendered/*.yaml "$recovery/raw-rendered/"
kubectl kustomize "$original/upstream/common/kubeflow-namespace/base" \
  >"$recovery/raw-rendered/kubeflow-namespace.yaml"

python scripts/prepare_module1_manifests.py --input-dir "$recovery/raw-rendered" \
  --output-dir "$recovery/rendered" --evidence "$recovery/manifest-preparation.json"
python scripts/render_module1_inventory.py --commit "$commit" \
  --output "$recovery/installation.json" \
  kubeflow-namespace="$recovery/rendered/kubeflow-namespace.yaml" \
  cert-manager="$recovery/rendered/cert-manager.yaml" \
  istio-crds="$recovery/rendered/istio-crds.yaml" \
  istio-namespace="$recovery/rendered/istio-namespace.yaml" \
  istio="$recovery/rendered/istio.yaml" \
  knative-serving="$recovery/rendered/knative-serving.yaml" \
  cluster-local-gateway="$recovery/rendered/cluster-local-gateway.yaml" \
  kserve="$recovery/rendered/kserve.yaml"
python -m scripts.verify_module1_upstream_inventory --output "$recovery/rendered-inventory.json" \
  "$recovery/rendered/kubeflow-namespace.yaml" "$recovery/rendered/cert-manager.yaml" \
  "$recovery/rendered/istio-crds.yaml" "$recovery/rendered/istio-namespace.yaml" \
  "$recovery/rendered/istio.yaml" "$recovery/rendered/knative-serving.yaml" \
  "$recovery/rendered/cluster-local-gateway.yaml" "$recovery/rendered/kserve.yaml"
find "$recovery/raw-rendered" "$recovery/rendered" -type f -name '*.yaml' -print0 | \
  sort -z | xargs -0 sha256sum >"$recovery/rendered-manifests.sha256"
cp "$original/kubeconfig" "$recovery/kubeconfig"
chmod 0600 "$recovery/kubeconfig"
chmod 0444 "$recovery"/raw-rendered/*.yaml "$recovery"/rendered/*.yaml \
  "$recovery/installation.json" "$recovery/manifest-preparation.json" \
  "$recovery/rendered-inventory.json" "$recovery/rendered-manifests.sha256" \
  "$recovery/original-evidence.sha256"

export KUBECONFIG="$recovery/kubeconfig"
[[ "$(kubectl config current-context)" == "$context" ]] || { echo "unexpected current context" >&2; exit 1; }
[[ "$(kind get clusters | grep -Fx "$cluster")" == "$cluster" ]] || { echo "exact disposable cluster is missing" >&2; exit 1; }
k=(kubectl --context "$context")
"${k[@]}" get namespace,sidecar.networking.istio.io,pod -A -o json \
  >"$recovery/pre-recovery-resources.json"

"${k[@]}" apply -f "$recovery/rendered/kubeflow-namespace.yaml"
"${k[@]}" apply -f "$recovery/rendered/cert-manager.yaml"
"${k[@]}" rollout status deployment/cert-manager-webhook -n cert-manager --timeout=180s
for manifest in istio-crds istio-namespace istio; do
  "${k[@]}" apply -f "$recovery/rendered/$manifest.yaml"
done
python scripts/module1_crd_order.py --execute --context "$context" \
  --manifest "$recovery/rendered/knative-serving.yaml" --component knative \
  --evidence-dir "$recovery/apply-stages/knative"
"${k[@]}" apply -f "$recovery/rendered/cluster-local-gateway.yaml"
python scripts/module1_crd_order.py --execute --context "$context" \
  --manifest "$recovery/rendered/kserve.yaml" --component kserve \
  --evidence-dir "$recovery/apply-stages/kserve" --server-side
"${k[@]}" wait --for=condition=Ready pods --all --all-namespaces \
  --timeout=300s --field-selector=status.phase!=Succeeded

"${k[@]}" create configmap cogniflow-serving-inventory -n kserve \
  --from-literal=source_commit="$commit" \
  --from-file=installation.json="$recovery/installation.json" \
  --dry-run=client -o yaml | "${k[@]}" apply -f -
"${k[@]}" patch configmap config-autoscaler -n knative-serving --type merge -p \
  '{"data":{"enable-scale-to-zero":"true","stable-window":"60s","scale-to-zero-grace-period":"30s"}}'
"${k[@]}" patch configmap config-defaults -n knative-serving --type merge -p \
  '{"data":{"revision-timeout-seconds":"35","revision-response-start-timeout-seconds":"35","revision-idle-timeout-seconds":"35"}}'
"${k[@]}" get namespace,sidecar.networking.istio.io,pod -A -o json \
  >"$recovery/post-recovery-resources.json"

jq -n --arg timestamp "$(date --iso-8601=ns)" \
  '{status:"PASS",finished_at:$timestamp}' >"$recovery/recovery-result.json"
trap - ERR
echo "Recovered only $context. Qualification and deletion still require separate authorization."
