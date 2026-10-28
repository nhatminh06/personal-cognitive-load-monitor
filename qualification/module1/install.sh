#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--execute" && $# == 3 && "$2" == "--evidence-dir" ]] || {
  echo "usage: install.sh --execute --evidence-dir NEW_DIRECTORY" >&2
  exit 2
}

commit=f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0
node_image=kindest/node:v1.34.11@sha256:44e222ee2132dab25ff87301682f89eb82c7880ea3a1bf543bfe9708fd08d67d
cluster=cogniflow-module1-qualification
context=kind-cogniflow-module1-qualification
evidence=$3
[[ "$evidence" == /* && "$evidence" != "$(pwd)"/* ]] || {
  echo "evidence directory must be an absolute path outside the repository" >&2
  exit 1
}
[[ ! -e "$evidence" ]] || { echo "evidence directory already exists" >&2; exit 1; }

python scripts/module1_qualification_preflight.py --execute --cluster "$cluster" \
  --context "$context" --workspace .
mkdir -m 0700 "$evidence"
export KUBECONFIG="$evidence/kubeconfig"
exec > >(tee "$evidence/install.log") 2>&1
failed() { jq -n --arg timestamp "$(date --iso-8601=ns)" '{status:"FAIL",finished_at:$timestamp}' >"$evidence/install-result.json"; }
trap failed ERR

git clone --filter=blob:none https://github.com/kubeflow/community-distribution.git "$evidence/upstream"
git -C "$evidence/upstream" checkout --detach "$commit"
actual_commit=$(git -C "$evidence/upstream" rev-parse HEAD)
[[ "$actual_commit" == "$commit" ]] || { echo "checked-out source commit mismatch" >&2; exit 1; }

mkdir -m 0700 "$evidence/raw-rendered"
cd "$evidence/upstream"
kubectl kustomize common/cert-manager/base >../raw-rendered/cert-manager.yaml
kubectl kustomize common/istio/istio-crds/base >../raw-rendered/istio-crds.yaml
kubectl kustomize common/istio/istio-namespace/base >../raw-rendered/istio-namespace.yaml
kubectl kustomize common/istio/istio-install/base >../raw-rendered/istio.yaml
kubectl kustomize common/knative/knative-serving/overlays/gateways >../raw-rendered/knative-serving.yaml
kubectl kustomize common/istio/cluster-local-gateway/base >../raw-rendered/cluster-local-gateway.yaml
kubectl kustomize applications/kserve/kserve >../raw-rendered/kserve.yaml
cd - >/dev/null

python scripts/prepare_module1_manifests.py --input-dir "$evidence/raw-rendered" \
  --output-dir "$evidence/rendered" --evidence "$evidence/manifest-preparation.json"
python scripts/render_module1_inventory.py --commit "$actual_commit" \
  --output "$evidence/installation.json" \
  cert-manager="$evidence/rendered/cert-manager.yaml" \
  istio-crds="$evidence/rendered/istio-crds.yaml" \
  istio-namespace="$evidence/rendered/istio-namespace.yaml" \
  istio="$evidence/rendered/istio.yaml" \
  knative-serving="$evidence/rendered/knative-serving.yaml" \
  cluster-local-gateway="$evidence/rendered/cluster-local-gateway.yaml" \
  kserve="$evidence/rendered/kserve.yaml"
python -m scripts.verify_module1_upstream_inventory --output "$evidence/rendered-inventory.json" \
  "$evidence/rendered/cert-manager.yaml" "$evidence/rendered/istio-crds.yaml" \
  "$evidence/rendered/istio-namespace.yaml" "$evidence/rendered/istio.yaml" \
  "$evidence/rendered/knative-serving.yaml" "$evidence/rendered/cluster-local-gateway.yaml" \
  "$evidence/rendered/kserve.yaml"
find "$evidence/raw-rendered" "$evidence/rendered" -type f -name '*.yaml' -print0 | \
  sort -z | xargs -0 sha256sum >"$evidence/rendered-manifests.sha256"
chmod 0444 "$evidence"/raw-rendered/*.yaml "$evidence"/rendered/*.yaml \
  "$evidence/installation.json" "$evidence/manifest-preparation.json" \
  "$evidence/rendered-inventory.json" "$evidence/rendered-manifests.sha256"

kind create cluster --name "$cluster" --image "$node_image" --wait 120s
[[ "$(kubectl config current-context)" == "$context" ]] || { echo "unexpected current context" >&2; exit 1; }
chmod 0600 "$KUBECONFIG"
kubectl --context "$context" cluster-info >"$evidence/cluster-info.txt"

for manifest in cert-manager istio-crds istio-namespace istio knative-serving cluster-local-gateway; do
  kubectl --context "$context" apply -f "$evidence/rendered/$manifest.yaml"
done
kubectl --context "$context" rollout status deployment/cert-manager-webhook -n cert-manager --timeout=180s
kubectl --context "$context" apply --server-side --force-conflicts -f "$evidence/rendered/kserve.yaml"
kubectl --context "$context" wait --for=condition=Ready pods --all --all-namespaces \
  --timeout=300s --field-selector=status.phase!=Succeeded

kubectl --context "$context" create configmap cogniflow-serving-inventory -n kserve \
  --from-literal=source_commit="$commit" \
  --from-file=installation.json="$evidence/installation.json"
kubectl --context "$context" patch configmap config-autoscaler -n knative-serving --type merge -p \
  '{"data":{"enable-scale-to-zero":"true","stable-window":"60s","scale-to-zero-grace-period":"30s"}}'
kubectl --context "$context" patch configmap config-defaults -n knative-serving --type merge -p \
  '{"data":{"revision-timeout-seconds":"35","revision-response-start-timeout-seconds":"35","revision-idle-timeout-seconds":"35"}}'

jq -n --arg timestamp "$(date --iso-8601=ns)" '{status:"PASS",finished_at:$timestamp}' >"$evidence/install-result.json"
trap - ERR
echo "Installed only in $context. Qualification and cluster deletion each require separate authorization."
