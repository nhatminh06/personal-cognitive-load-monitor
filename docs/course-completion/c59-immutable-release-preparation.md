# C5.9 immutable release preparation

**Date:** 2026-11-17

**Source revision:** `b3b34e2ed10e1747a96ba632ceddefa108c2cd19`

**Decision:** **BLOCKED — publication is not authorized and C5.3 raw evidence is absent**

This packet prepares, but does not perform, registry publication, signing,
attestation, Kubernetes mutation, runner registration, model approval, or cloud
deployment. M10.3 remains deployment NO-GO and SEC-022 is unchanged.

## Verified local artifacts

`deploy/releases/c59-local-artifacts.json` is the machine-readable ledger. A
local OCI index ID, its runnable platform manifest, and a remote registry
manifest digest are different identities. A local `RepoDigest` without a
registry hostname is not a remote deployment identity.

| Artifact | Local OCI index ID | Local linux/amd64 runtime manifest | Local evidence | Release state |
|---|---|---|---|---|
| Deployment runner | `sha256:fea8be5e98ba4defff5f8d23059c9d31103f7014b4e33b42c1aa1dcb0498d44a` | `sha256:3aab5b8fe68d83df3608c6cb1f7b3c1b02798643c068345344a56b8816b2b182` | C5.8 raw Trivy, SPDX and BuildKit metadata exist and their SHA-256 values match the qualification record | Locally qualified; unpublished |
| FastAPI | `sha256:9609981bd9c775b3937a0d8cf7158c02e786089cd35ce1de5352d90b4ace26c0` | Not retained independently | Image exists and C5.3 records 0 HIGH/0 CRITICAL plus isolated runtime PASS; the raw Trivy, SPDX and provenance files are absent | Blocked |
| KServe | `sha256:6e4a0d3c3682fec3c85e3676acb268d422819f5378494f3b26e78ad99cba3f9b` | Not retained independently | Image exists and C5.3 records 0 HIGH/0 CRITICAL plus isolated runtime PASS; the raw Trivy, SPDX and provenance files are absent | Blocked |

The verified C5.8 evidence digests are Trivy
`81924597d2acb40c89350e2e13d3b0481c1c26b95ef6475e08e607a7374217a2`,
SPDX `1f1c578b6c191a87bb8e7355930e732db996e62c6069f2679b44605bf8aa9736`,
and BuildKit metadata
`394ce1aa17e5f6a7c0faab57bc450e453b35718b3eae307f067bd07302a64bac`.
The source-built runner must be described as Actions Runner 2.338.0 at commit
`a9dcf1bf7a78751648ff630fd4d0152471293487`, package SHA-256
`6d552c6b6acf854247f0b4c439586dd53196f54b94ba8320c76696d6a18d2e46`;
it is not an official GitHub binary release.

## Proposed Artifact Registry layout

The existing Terraform defines the private Docker repository
`us-central1-docker.pkg.dev/$PROJECT_ID/cogniflow-images`. Proposed image paths
are:

- `.../cogniflow-deploy-runner@sha256:$REMOTE_INDEX_DIGEST`
- `.../cognitive-load-api@sha256:$REMOTE_INDEX_DIGEST`
- `.../cogniflow-kserve@sha256:$REMOTE_INDEX_DIGEST`

A commit-derived tag may be used only as a temporary publication handle.
Kubernetes, evidence, rollback, and signature commands must use the resolved
remote `repository@sha256:...` reference. Signatures and attestations are
separate registry objects bound by subject digest; their identities do not
replace the image digest.

## Owner-authorized publication and verification

Prerequisites are an owner-approved GCP project, existing private
`cogniflow-images` repository, protected `production-release` environment,
GitHub OIDC with `id-token: write`, and the Terraform release service account.
That account has only repository `roles/artifactregistry.writer`; independent
verification needs `roles/artifactregistry.reader`. No service-account key is
permitted. The owner must also approve this exact Git commit and all three local
identities.

Before publication, restore or independently regenerate the two missing C5.3
raw evidence sets from the exact loaded images. Generate fresh SPDX SBOMs and
complete Trivy JSON reports, require zero HIGH/CRITICAL and no scanner error,
record checksums, and resolve each local linux/amd64 runtime descriptor. Any
different index or runnable manifest requires a new qualification decision.

In an authorized protected job, use values reviewed out of band:

```bash
set -euo pipefail
test "$GITHUB_SHA" = b3b34e2ed10e1747a96ba632ceddefa108c2cd19
REGISTRY="us-central1-docker.pkg.dev/${GCP_PROJECT_ID}/cogniflow-images"
RELEASE_TAG="git-${GITHUB_SHA}"
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

publish() {
  local source=$1 name=$2 expected_local_index=$3
  test "$(docker image inspect "$source" --format '{{.Id}}')" = "$expected_local_index"
  docker tag "$source" "$REGISTRY/$name:$RELEASE_TAG"
  docker push "$REGISTRY/$name:$RELEASE_TAG"
  gcloud artifacts docker images describe "$REGISTRY/$name:$RELEASE_TAG" \
    --format='value(image_summary.digest)'
}

publish cogniflow-deploy-runner:c58-qualified cogniflow-deploy-runner \
  sha256:fea8be5e98ba4defff5f8d23059c9d31103f7014b4e33b42c1aa1dcb0498d44a
publish cognitive-load-api:c53-wolfi cognitive-load-api \
  sha256:9609981bd9c775b3937a0d8cf7158c02e786089cd35ce1de5352d90b4ace26c0
publish cogniflow-kserve:c53-wolfi cogniflow-kserve \
  sha256:6e4a0d3c3682fec3c85e3676acb268d422819f5378494f3b26e78ad99cba3f9b
```

For each printed digest, set `IMAGE` to the exact remote digest reference and
preserve `docker buildx imagetools inspect "$IMAGE" --raw`. Verify its
linux/amd64 descriptor against the independently recorded local runtime
descriptor; for the runner it must be
`sha256:3aab5b8fe68d83df3608c6cb1f7b3c1b02798643c068345344a56b8816b2b182`.
Then:

```bash
cosign sign --yes "$IMAGE"
cosign attest --yes --type spdxjson --predicate "$SBOM" "$IMAGE"
cosign attest --yes --type slsaprovenance --predicate "$PROVENANCE" "$IMAGE"
cosign verify --certificate-identity-regexp "$EXPECTED_WORKFLOW_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com "$IMAGE"
cosign verify-attestation --type spdxjson \
  --certificate-identity-regexp "$EXPECTED_WORKFLOW_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com "$IMAGE"
cosign verify-attestation --type slsaprovenance \
  --certificate-identity-regexp "$EXPECTED_WORKFLOW_IDENTITY" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com "$IMAGE"
trivy image --severity HIGH,CRITICAL --exit-code 1 --format json \
  --output "$EVIDENCE/$(basename "${IMAGE%@*}").remote.trivy.json" "$IMAGE"
```

Record the remote digest, remote raw manifest SHA-256, signature certificate
identity, Rekor bundle, attestation digests, fresh scan checksum/database time,
and verified local runtime descriptor. Run
`scripts/verify_cloud_release.sh` on all exact remote references. Do not update
Helm or runner manifests from a tag.

## Owner-authorized KServe infrastructure acceptance

This test is limited to the disposable legacy `qualification-model`, version
`1`. Its dataset and registered-artifact digest is
`2fc87bece39ad5f76a8a2e6ee74fd830d7012f447b0cbdc8f2823124e95c0133`;
the C5.3 packaged model SHA-256 is
`835500f0f3ab99b0c3a2fd430fa7a020dec3c1b5514e7d51a4136b340c928e85`.
It is infrastructure evidence only and is not the C2.2 candidate.

Require separate owner authorization for the exact kubeconfig/context, the two
ConfigMap mutations, the three remote image digests, test traffic, and one
predictor-pod restart. Capture the current objects first:

```bash
kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" -n kserve \
  get configmap inferenceservice-config -o json > "$EVIDENCE/kserve-before.json"
kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" -n knative-serving \
  get configmap config-istio -o json > "$EVIDENCE/knative-before.json"
kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" \
  get gateways.networking.istio.io -A -o json > "$EVIDENCE/gateways.json"
```

The reviewed correction changes only KServe ingress/local gateways to
`istio-system/istio-ingressgateway` and
`knative-serving/knative-local-gateway`, and removes
`gateway.kubeflow.kubeflow-gateway` from Knative `config-istio`. Generate patch
payloads from the captured values, review them, then patch only after approval:

```bash
jq -c '.data.ingress | fromjson |
  .ingressGateway="istio-system/istio-ingressgateway" |
  .localGateway="knative-serving/knative-local-gateway"' \
  "$EVIDENCE/kserve-before.json" > "$EVIDENCE/kserve-ingress.json"
jq -cn --rawfile ingress "$EVIDENCE/kserve-ingress.json" \
  '{data:{ingress:($ingress|fromjson|tojson)}}' > "$EVIDENCE/kserve-patch.json"
kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" -n kserve patch \
  configmap inferenceservice-config --type merge \
  --patch-file "$EVIDENCE/kserve-patch.json"
kubectl --kubeconfig "$KUBECONFIG" --context "$CONTEXT" -n knative-serving patch \
  configmap config-istio --type json \
  --patch='[{"op":"remove","path":"/data/gateway.kubeflow.kubeflow-gateway"}]'
```

Re-capture both ConfigMaps and run `scripts/validate_kserve_gateways.py`. Confirm
controller health and a cluster-local InferenceService URL. Review the rendered
NetworkPolicies before apply: API ingress is TCP 8000 from the approved ingress
or observability namespace; API egress to KServe is TCP 80/8080; predictor
ingress is TCP 8080 plus Knative queue-proxy 8012 from the API/Knative-serving
paths. Reject broader effective access.

Use the exact published FastAPI/KServe digests and the disposable identity with
the existing Module I render/qualification procedure. Capture server-side
dry-run output before the authorized Helm mutation. From the restricted
qualification client, require metadata identity, a direct six-feature KServe
prediction, authenticated FastAPI `/ready`, `/model-info`, and `/predict`, plus
401 for a bad key. During the authorized deletion of one predictor pod, require
FastAPI readiness to fail closed without a local fallback; wait for the same
image/model identities to recover and repeat both predictions. Preserve
conditions, Routes, Services, pod image IDs, events, logs, timestamps, and
recovery duration.

Rollback uses the captured ConfigMap values, not guessed defaults. Restore
`.data.ingress` from `kserve-before.json` and the exact legacy Knative key/value
from `knative-before.json` with merge patches, then roll Helm back to the
captured revision. Verify the previous digests, gateway state, readiness, and
NetworkPolicies. Do not delete shared controllers, namespaces, or either kind
cluster.

## Remaining gates

1. Restore or regenerate and verify exact C5.3 raw scan/SBOM/provenance evidence.
2. Supply the owner-approved GCP project, protected-environment reviewers and
   OIDC release identity; create nothing during this milestone.
3. Publish exact bytes, resolve and compare remote manifests, sign, attest, and
   freshly scan the remote digest references.
4. Obtain separate owner approval for the scoped gateway correction, published
   images, legacy-model traffic, restart test, and rollback.
5. Keep C2.2 unapproved and undeployed. Local qualification does not approve
   M10.3 cloud deployment.
