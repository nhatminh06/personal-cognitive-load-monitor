#!/usr/bin/env bash
set -euo pipefail

action=${1:-}
[[ "$action" =~ ^(plan|deploy|rollback|teardown)$ ]] || {
  echo "usage: $0 plan|deploy|rollback|teardown" >&2; exit 2;
}
required=(KUBE_CONTEXT KUBECONFIG NAMESPACE RELEASE API_IMAGE KSERVE_IMAGE SOURCE_COMMIT MODEL_NAME MODEL_VERSION MODEL_SHA256 MODEL_ARTIFACT_SHA256 MODEL_DATASET_SHA256 MODEL_FEATURE_SCHEMA_VERSION MODEL_PACKAGE_SHA256 MODEL_APPROVAL_STATUS OWNER_AUTHORIZATION)
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "$name is required" >&2; exit 2; }
done
[[ "$KUBE_CONTEXT" != *cogniflow-module1-qualification* && "$KUBE_CONTEXT" != *cogniflow-local* ]] || {
  echo "protected kind contexts are forbidden" >&2; exit 2;
}
[[ "$KUBE_CONTEXT" =~ ^[A-Za-z0-9._/-]+$ && "$NAMESPACE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && "$RELEASE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
  echo "context, namespace or release is invalid" >&2; exit 2;
}
[[ "$API_IMAGE" =~ ^[a-z0-9-]+-docker\.pkg\.dev/[a-z0-9-]+/cogniflow-images/cognitive-load-api@sha256:[a-f0-9]{64}$ ]] || {
  echo "API_IMAGE must be an immutable Artifact Registry digest" >&2; exit 2;
}
[[ "$KSERVE_IMAGE" =~ ^[a-z0-9-]+-docker\.pkg\.dev/[a-z0-9-]+/cogniflow-images/cogniflow-kserve@sha256:[a-f0-9]{64}$ ]] || {
  echo "KSERVE_IMAGE must be an immutable Artifact Registry digest" >&2; exit 2;
}
[[ "$SOURCE_COMMIT" =~ ^[a-f0-9]{40}$ && "$MODEL_PACKAGE_SHA256" =~ ^[a-f0-9]{64}$ && "$MODEL_SHA256" =~ ^[a-f0-9]{64}$ && "$MODEL_ARTIFACT_SHA256" =~ ^[a-f0-9]{64}$ && "$MODEL_DATASET_SHA256" =~ ^[a-f0-9]{64}$ ]] || {
  echo "source and model identities must be exact digests" >&2; exit 2;
}
[[ "$MODEL_NAME" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ && "$MODEL_VERSION" =~ ^[1-9][0-9]*$ ]] || {
  echo "model name and version are invalid" >&2; exit 2;
}
[[ "$MODEL_APPROVAL_STATUS" == approved ]] || { echo "model approval is required" >&2; exit 2; }
[[ "$OWNER_AUTHORIZATION" == "DEPLOY:${SOURCE_COMMIT}:${MODEL_PACKAGE_SHA256}:${KUBE_CONTEXT}:${NAMESPACE}:${RELEASE}:${action}" ]] || {
  echo "owner authorization is not bound to this exact action" >&2; exit 2;
}
if [[ "$action" == rollback ]]; then
  [[ "${ROLLBACK_REVISION:-}" =~ ^[1-9][0-9]*$ ]] || { echo "ROLLBACK_REVISION is required" >&2; exit 2; }
fi

printf 'action=%s\ncontext=%s\nnamespace=%s\nrelease=%s\napi=%s\nkserve=%s\nsource=%s\nmodel_package=%s\n' \
  "$action" "$KUBE_CONTEXT" "$NAMESPACE" "$RELEASE" "$API_IMAGE" "$KSERVE_IMAGE" "$SOURCE_COMMIT" "$MODEL_PACKAGE_SHA256"
[[ "$action" == plan ]] && exit 0
[[ "${EXECUTE:-}" == "authorized" ]] || { echo "mutation requires EXECUTE=authorized" >&2; exit 2; }
[[ -n "${EVIDENCE_DIR:-}" && -d "$EVIDENCE_DIR" && ! -L "$EVIDENCE_DIR" ]] || {
  echo "EVIDENCE_DIR must be a pre-created real directory" >&2; exit 2;
}
umask 077

export KUBECONFIG
kubectl --context "$KUBE_CONTEXT" auth can-i get namespaces >/dev/null
case "$action" in
  deploy)
    scripts/verify_cloud_release.sh "$API_IMAGE" "$KSERVE_IMAGE"
    api_repo=${API_IMAGE%@*}; api_digest=${API_IMAGE#*@}
    kserve_repo=${KSERVE_IMAGE%@*}; kserve_digest=${KSERVE_IMAGE#*@}
    helm upgrade --install "$RELEASE" ./helm/cognitive-load-monitor \
      --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE" --atomic --wait --timeout 10m --history-max 10 \
      --set image.repository="$api_repo" --set image.digest="$api_digest" \
      --set kserve.enabled=true --set kserve.image.repository="$kserve_repo" \
      --set kserve.image.digest="$kserve_digest" --set config.inferenceMode=kserve \
      --set config.modelName="$MODEL_NAME" --set config.modelVersion="$MODEL_VERSION" \
      --set config.modelSha256="$MODEL_SHA256" --set config.modelArtifactSha256="$MODEL_ARTIFACT_SHA256" \
      --set config.modelDatasetSha256="$MODEL_DATASET_SHA256" \
      --set config.modelFeatureSchemaVersion="$MODEL_FEATURE_SCHEMA_VERSION"
    kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" rollout status deployment/"$RELEASE" --timeout=5m
    kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" wait --for=condition=Ready \
      inferenceservice/cognitive-load-classifier --timeout=10m
    ;;
  rollback)
    helm rollback "$RELEASE" "$ROLLBACK_REVISION" --kube-context "$KUBE_CONTEXT" \
      --namespace "$NAMESPACE" --wait --timeout 10m
    helm status "$RELEASE" --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE" >/dev/null
    ;;
  teardown)
    helm uninstall "$RELEASE" --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE" --wait
    if helm status "$RELEASE" --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE" >/dev/null 2>&1; then
      echo "release still exists after teardown" >&2; exit 1
    fi
    ;;
esac

evidence="$EVIDENCE_DIR/${action}-${SOURCE_COMMIT}.json"
[[ ! -e "$evidence" ]] || { echo "evidence already exists: $evidence" >&2; exit 1; }
temporary="$evidence.tmp"
printf '{"action":"%s","context":"%s","namespace":"%s","release":"%s","source_commit":"%s","api_image":"%s","kserve_image":"%s","model_name":"%s","model_version":"%s","model_sha256":"%s","model_artifact_sha256":"%s","model_dataset_sha256":"%s","model_package_sha256":"%s","result":"passed"}\n' \
  "$action" "$KUBE_CONTEXT" "$NAMESPACE" "$RELEASE" "$SOURCE_COMMIT" "$API_IMAGE" "$KSERVE_IMAGE" "$MODEL_NAME" "$MODEL_VERSION" "$MODEL_SHA256" "$MODEL_ARTIFACT_SHA256" "$MODEL_DATASET_SHA256" "$MODEL_PACKAGE_SHA256" >"$temporary"
mv "$temporary" "$evidence"
