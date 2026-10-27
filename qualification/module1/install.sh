#!/usr/bin/env bash
set -euo pipefail

commit=f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0
node_image=kindest/node:v1.34.11@sha256:44e222ee2132dab25ff87301682f89eb82c7880ea3a1bf543bfe9708fd08d67d
cluster=cogniflow-module1-qualification
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

git clone --filter=blob:none https://github.com/kubeflow/community-distribution.git "$workdir/upstream"
git -C "$workdir/upstream" checkout --detach "$commit"
test "$(git -C "$workdir/upstream" rev-parse HEAD)" = "$commit"
kind create cluster --name "$cluster" --image "$node_image" --wait 120s

cd "$workdir/upstream"
kustomize build common/cert-manager/base | kubectl apply -f -
kubectl rollout status deployment/cert-manager-webhook -n cert-manager --timeout=180s
kustomize build common/istio/istio-crds/base | kubectl apply -f -
kustomize build common/istio/istio-namespace/base | kubectl apply -f -
kustomize build common/istio/istio-install/base | kubectl apply -f -
kustomize build common/knative/knative-serving/overlays/gateways | kubectl apply -f -
kustomize build common/istio/cluster-local-gateway/base | kubectl apply -f -
kustomize build applications/kserve/kserve | kubectl apply --server-side --force-conflicts -f -
kubectl wait --for=condition=Ready pods --all --all-namespaces --timeout=300s --field-selector=status.phase!=Succeeded

kubectl create configmap cogniflow-serving-inventory -n kserve \
  --from-literal=source_commit="$commit" \
  --from-literal=charts='{"cert-manager":"1.21.2","istio-base":"1.31.3","istiod":"1.31.3","knative-serving":"1.23.0","kserve-crd":"0.21.0","kserve-resources":"0.21.0"}'

kubectl patch configmap config-autoscaler -n knative-serving --type merge -p \
  '{"data":{"enable-scale-to-zero":"true","stable-window":"60s","scale-to-zero-grace-period":"30s"}}'
kubectl patch configmap config-defaults -n knative-serving --type merge -p \
  '{"data":{"revision-timeout-seconds":"35","revision-response-start-timeout-seconds":"35","revision-idle-timeout-seconds":"35"}}'

echo "Installed disposable stack only. Run qualification/module1/qualify.sh separately."
