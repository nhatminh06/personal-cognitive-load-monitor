# Module III Phase 3: secure local model serving

## Boundaries

Phase 3 packages exactly one explicitly approved MLflow model and provides an isolated local-kind deployment path. It does not approve models, deploy candidates, modify the Terraform-owned `cognitive-load-monitor` release, or introduce GCP, Spark, KServe, Kubeflow, Knative, or Argo CD.

```text
local MLflow model name + exact version + expected artifact-tree SHA-256
  -> require approved registry status and approval audit tags
  -> download exact registered source and verify the complete artifact tree
  -> validate skops format and run provenance
  -> copy model.skops only; write immutable package manifest and model SHA-256
  -> build dedicated image
  -> isolated Helm release/namespace (ClusterIP)
  -> loopback port-forward on 127.0.0.1:18001
```

The existing Terraform-managed demo release remains in namespace `cognitive-load` and continues to use host port 18000. The experimental release is `cognitive-load-phase3` in namespace `cognitive-load-phase3`. Terraform must never manage the experimental release.

## Approved model packaging

The current Phase 2 model is only a candidate and must not be packaged. After an owner separately approves an exact version, package it without deserializing the registry artifact:

```fish
set tracking_uri sqlite:///mlflow-phase2.db
set model_name cognitive-load-classifier-phase2
set model_version APPROVED_VERSION
set artifact_sha256 APPROVED_REGISTERED_ARTIFACT_SHA256

env PYTHONPATH=src uv run python scripts/package_approved_model.py \
  --tracking-uri $tracking_uri \
  --model-name $model_name \
  --version $model_version \
  --expected-artifact-digest $artifact_sha256 \
  --output-dir build/model-package
```

The command fails unless registry identity, approval tags, run provenance, expected digest, downloaded artifact-tree digest, MLflow flavor, and model layout all match. `build/model-package/model-package.json` records the registered artifact digest separately from the packaged model digest. Generated packages remain ignored by Git.

At runtime the API validates that manifest before deserialization. The model file digest must match both the manifest and deployment configuration; model name, exact version, registered artifact digest, dataset digest, feature schema, and canonical six-feature order must also agree. `/ready` fails closed and `/model-info` returns HTTP 503 until this succeeds. Once verified, `/model-info` reports the manifest-backed provenance rather than raw environment values.

## Image and Helm validation

Build only after packaging succeeds:

```fish
set image_tag (git rev-parse HEAD)
set image_repository localhost/cognitive-load-api-phase3
set image_archive /tmp/cognitive-load-api-phase3.oci
docker buildx build --file Dockerfile.model-serving \
  --tag $image_repository:$image_tag \
  --output type=oci,dest=$image_archive .
set image_digest (tar -xOf $image_archive index.json | jq --raw-output '.manifests[0].digest')
string match --regex --quiet '^sha256:[a-f0-9]{64}$' $image_digest
kind load image-archive --name cogniflow-local $image_archive
docker exec cogniflow-local-control-plane crictl inspecti $image_repository@$image_digest
```

The serving Dockerfile copies only `cognitive_load_model.skops` and its package manifest. The OCI index supplies the repository manifest digest; the final `crictl inspecti` proves that exact `repository@sha256:...` reference resolves in kind's containerd before Helm is allowed to use it with `imagePullPolicy: Never`. Stop if that check fails. Never use `docker image inspect .Id`, a config digest, or any other Docker image ID as the repository digest.

Set the cluster identity once and pass it to every Kubernetes client command:

```fish
set kubeconfig infra/terraform/local/.kube/cogniflow-local.yaml
set kube_context kind-cogniflow-local
kubectl --kubeconfig $kubeconfig --context $kube_context config current-context
```

Validate the chart before installation:

```fish
helm lint helm/cognitive-load-monitor \
  --kubeconfig $kubeconfig --kube-context $kube_context \
  --values helm/cognitive-load-monitor/values.phase3-local.yaml \
  --set-string image.digest=sha256:IMAGE_DIGEST \
  --set-string config.modelVersion=$model_version \
  --set-string config.modelSha256=PACKAGED_MODEL_SHA256 \
  --set-string config.modelArtifactSha256=$artifact_sha256 \
  --set-string config.modelDatasetSha256=DATASET_SHA256

helm template cognitive-load-phase3 helm/cognitive-load-monitor \
  --kubeconfig $kubeconfig --kube-context $kube_context \
  --namespace cognitive-load-phase3 \
  --values helm/cognitive-load-monitor/values.phase3-local.yaml \
  --set-string image.digest=sha256:IMAGE_DIGEST \
  --set-string config.modelVersion=$model_version \
  --set-string config.modelSha256=PACKAGED_MODEL_SHA256 \
  --set-string config.modelArtifactSha256=$artifact_sha256 \
  --set-string config.modelDatasetSha256=DATASET_SHA256
```

Create the API-key Secret from a protected local file, then install only after reviewing the rendered manifest. Never place the key in values or shell history.

```fish
kubectl --kubeconfig $kubeconfig --context $kube_context \
  create namespace cognitive-load-phase3
kubectl --kubeconfig $kubeconfig --context $kube_context \
  create secret generic cognitive-load-phase3-api-key \
  --namespace cognitive-load-phase3 \
  --from-file=COGNIFLOW_API_KEY=/secure/path/cogniflow-api-key

helm upgrade --install cognitive-load-phase3 helm/cognitive-load-monitor \
  --kubeconfig $kubeconfig --kube-context $kube_context \
  --namespace cognitive-load-phase3 \
  --values helm/cognitive-load-monitor/values.phase3-local.yaml \
  --set-string image.repository=$image_repository \
  --set-string image.digest=$image_digest \
  --set-string config.modelVersion=$model_version \
  --set-string config.modelSha256=PACKAGED_MODEL_SHA256 \
  --set-string config.modelArtifactSha256=$artifact_sha256 \
  --set-string config.modelDatasetSha256=DATASET_SHA256 \
  --atomic --wait --timeout 180s

kubectl --kubeconfig $kubeconfig --context $kube_context \
  port-forward --address 127.0.0.1 \
  --namespace cognitive-load-phase3 service/cognitive-load-phase3 18001:80
```

This release remains `ClusterIP`, has no ingress or NodePort, uses non-root UID 10001, a read-only root filesystem, dropped capabilities, and bounded resources.

## Runtime verification

With `api_key` loaded locally without printing it:

```fish
curl --fail http://127.0.0.1:18001/health
curl --fail http://127.0.0.1:18001/ready
curl --fail --header "X-API-Key: $api_key" http://127.0.0.1:18001/model-info
curl --fail http://127.0.0.1:18001/metrics
curl --fail --request POST --header "X-API-Key: $api_key" \
  --header "Content-Type: application/json" \
  --data '{"focus_minutes":120,"distraction_minutes":30,"tasks_due":3,"hours_to_deadline":24}' \
  http://127.0.0.1:18001/predict
```

Verify restart recovery with the explicitly targeted commands below. Corrupted, absent, or digest-mismatched models must keep `/ready` at HTTP 503 and `/predict` must never fall back to `demo_rule`.

```fish
kubectl --kubeconfig $kubeconfig --context $kube_context \
  rollout restart deployment/cognitive-load-phase3 --namespace cognitive-load-phase3
kubectl --kubeconfig $kubeconfig --context $kube_context \
  rollout status deployment/cognitive-load-phase3 \
  --namespace cognitive-load-phase3 --timeout 180s
```

For K9s, start with the exact context and namespace:

```fish
k9s --kubeconfig $kubeconfig --context $kube_context --namespace cognitive-load-phase3
```

Inspect `:pods`, `:deployments`, `:services`, `:events`, and pod logs with `l`. Confirm the image contains `@sha256:`, probes are healthy, restarts stabilize, and no Ingress, NodePort, KServe, Spark, or unexpected Secret values appear.

## Rollback and cleanup

List and roll back only the isolated release:

```fish
helm history cognitive-load-phase3 --namespace cognitive-load-phase3 \
  --kubeconfig $kubeconfig --kube-context $kube_context
helm rollback cognitive-load-phase3 PREVIOUS_REVISION \
  --namespace cognitive-load-phase3 --wait \
  --kubeconfig $kubeconfig --kube-context $kube_context
```

The original demo remains available through its independent loopback port-forward on 127.0.0.1:18000.

To remove the experiment, stop only its 18001 port-forward, then use only the explicitly targeted commands below. Verify the namespace contains no unrelated resources before deletion.

```fish
helm uninstall cognitive-load-phase3 --namespace cognitive-load-phase3 \
  --kubeconfig $kubeconfig --kube-context $kube_context
kubectl --kubeconfig $kubeconfig --context $kube_context \
  get all --namespace cognitive-load-phase3
kubectl --kubeconfig $kubeconfig --context $kube_context \
  delete namespace cognitive-load-phase3
```

Never destroy the kind cluster, Terraform state, `cognitive-load`, PersonalOS, or Docker volumes.

## Current verification status

The packaging, loader, provenance endpoint, negative security paths, and Helm rendering are locally testable without approval. Live image build, release installation, runtime endpoint checks, restart recovery, and K9s inspection remain blocked until an owner explicitly approves a model version with the registered artifact digest.

Verified locally on October 26, 2026:

- Full regression: 152 passed with 89.41% combined coverage (81% gate); Ruff and MyPy passed.
- DVC reported all pipelines up to date.
- The actual Phase 2 joblib export loaded through the production client and returned LOW, MEDIUM, and HIGH for deterministic samples.
- The packaging command rejected model version 2 because it remains `candidate`, exited non-zero, and created no package.
- Helm lint and Phase 3 rendering passed; the chart rejected a missing image digest.
- The rendered ConfigMap, ServiceAccount, ClusterIP Service, and Deployment passed server-side dry-run validation against `kind-cogniflow-local`.
- Both local Terraform stages validated without applying or changing state.
- Trivy 0.76.1 reported zero HIGH/CRITICAL Dockerfile misconfigurations.
- The existing Terraform-owned demo deployment remained 1/1 Ready and passed `/health`, `/ready`, and `/model-info` through a temporary 127.0.0.1:18000 port-forward, which was then stopped.
- K9s 0.51.0 is installed. Phase 3 pod/log/event inspection was not performed because no experimental release was installed.
- MLflow version 2 metadata was inspected without deserialization: it is a `skops` model (`model.skops`) declaring only `sklearn.tree._tree.Tree` as trusted; it remains a candidate.
- The locked environment resolves `skops.io` 0.16.0, and a disposable random-forest skops round trip passed the same manifest, digest, feature-contract, and trusted-type loader used by the API.

No packaged-model digest or serving-image digest exists yet because producing them requires an explicitly approved model. The verified candidate registered-artifact digest remains `13137be7ce4c885877d7968afa0177be31cff60a4b2e33707893a7698c3b62ae`; it is not deployment authorization.
