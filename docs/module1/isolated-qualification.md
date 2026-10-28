# Module I isolated KServe qualification

Status: **BLOCKED**. No disposable cluster qualification was run and no candidate is `QUALIFIED`.

## Immutable upstream candidate

The candidate is Kubeflow Community Distribution commit
[`f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0`](https://github.com/kubeflow/community-distribution/tree/f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0),
not mutable `master`. Its manifests declare KServe 0.21.0, Knative Serving 1.23.0,
Istio 1.31.3 and cert-manager 1.21.2. The disposable cluster is separately pinned to
Kubernetes 1.34.11 by the kind node image digest in `qualification/module1/install.sh`.
The matrix policy is exact-patch and explicitly sets `gke_accepted: false`; no other kind
patch or GKE build is equivalent to this qualification.

The pinned source contains Kustomize installations plus unused Helm sources for some
components. This procedure installs Kustomize renders, not Helm releases. Qualification
inventory includes three required KServe workloads (excluding both disabled optional node
agents), six Knative/net-istio
controllers, Istiod, the Istio gateway and CNI, all three cert-manager controllers, all 38
rendered serving CRDs, immutable render hashes, exact resource identities, and
runtime-resolved image digests. The
protected preflight rejects a missing controller, mutable or different image, missing CRD,
chart mismatch, source-commit mismatch, version drift, or autoscaler drift.

## Upstream evidence and limits

The dedicated [`kserve_test.yaml`](https://github.com/kubeflow/community-distribution/blob/f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0/.github/workflows/kserve_test.yaml)
installs a real stack and runs real sklearn `InferenceService` predictions. Successful PR
runs exist, including [run 40484164700](https://github.com/kubeflow/community-distribution/actions/runs/40484164700).
There is no successful `master` KServe run for the pinned commit. The workflow currently
creates its default kind version rather than Kubernetes 1.34; the repository's full matrix
tests 1.35 and 1.37. Its curl test also accepts HTTP 404/503 on an authenticated route and
temporarily applies an allow-all workload `AuthorizationPolicy`. Those facts are useful
upstream evidence, but none proves CogniFlow readiness, strict prediction success,
scale-to-zero, cold activation, Kubernetes 1.34, or GKE.

Kubernetes 1.34 is supported by the pinned kind image, but GKE remains unverified. The
distribution has a GKE Istio CNI overlay because GKE's CNI path differs; the kind run does
not validate that overlay, GKE Dataplane V2 NetworkPolicy behavior, Workload Identity,
managed control-plane constraints, or the exact intended GKE patch version. A later,
separately authorized GKE qualification is still required before a protected GKE deploy.

## CogniFlow comparison and isolation

CogniFlow keeps Module III on KServe `Standard`; only
`values.module1-knative.yaml` selects Knative/KPA. The chart uses a digest-only custom
runtime, non-root user, read-only root filesystem, dropped capabilities, RuntimeDefault
seccomp, an isolated service account, bounded resources, and explicit KPA annotations.
Its NetworkPolicy permits predictor ingress only from the API pods and `knative-serving`
on ports 8080/8012, and egress only to GKE metadata and DNS. Unlike upstream's test, this
procedure installs no oauth2-proxy sample, default password, permissive predictor
AuthorizationPolicy, KServe UI, profile controller, Pipelines, Eventing, or sample model.

Istio CNI writes CNI configuration on nodes and therefore remains a privileged
cluster component even though the rendered container does not set
`securityContext.privileged`; KServe's local-model hostPath node-agent is not installed.
Cluster-scoped CRDs, webhooks and RBAC remain high-impact and are confined to a disposable
cluster. Seven allow-all policies rendered upstream are limited to named Istio/Knative
control-plane selectors and are inventoried for review; the verifier rejects any additional
allow-all policy, and no such policy is created for the qualification namespace or predictor.
The high-severity
[`GHSA-v824-8gxh-pgjw`](https://github.com/kubeflow/community-distribution/security/advisories/GHSA-v824-8gxh-pgjw)
depends on Kubeflow editor/profile permissions to create Istio routing resources. This
minimal procedure installs neither those roles nor profiles, and its qualification service
account receives no RoleBinding. The captured `kubectl auth can-i --list` output must
confirm that boundary. Before production review, attach Trivy/OSV results for every
runtime-resolved digest.

## Authorized run sequence

Do not run these commands against an existing context. A reviewer must authorize the
disposable run, verify the context name after installation, and then:

1. Authorize installation separately, then run
   `qualification/module1/install.sh --execute --evidence-dir NEW_PRIVATE_DIRECTORY`.
   Preflight refuses an existing cluster/context and requires at least 10 GiB available RAM,
   10 GiB Docker memory, 4 CPUs and 30 GiB free disk. Expected peak RAM is 12 GiB, within
   the 16 GiB local budget. Every `kubectl` operation is bound to
   `kind-cogniflow-module1-qualification`; kind writes only to the private
   `NEW_PRIVATE_DIRECTORY/kubeconfig`, never the user's default kubeconfig.
2. Generate `build/model-package` with
   `PYTHONPATH=src uv run python scripts/generate_qualification_model.py build/model-package`; build the
   KServe image locally, load it into kind, and set `KSERVE_IMAGE` to its immutable
   manifest digest. Do not publish it. The separately authorized commands are:

   ```bash
   EVIDENCE=/absolute/path/to/the/existing/install-evidence
   PYTHONPATH=src UV_CACHE_DIR=/tmp/cogniflow-qualification-uv \
     uv run --offline python scripts/generate_qualification_model.py build/model-package
   docker buildx build --platform linux/amd64 --load \
     --metadata-file "$EVIDENCE/qualification-image-metadata.json" \
     --file Dockerfile.kserve --tag cogniflow-kserve:qualification .
   export KSERVE_IMAGE="docker.io/library/cogniflow-kserve@$(
     jq -er '."containerimage.digest" | select(test("^sha256:[a-f0-9]{64}$"))' \
       "$EVIDENCE/qualification-image-metadata.json"
   )"
   KUBECONFIG="$EVIDENCE/kubeconfig" kind load docker-image \
     --name cogniflow-module1-qualification "$KSERVE_IMAGE"
   docker exec cogniflow-module1-qualification-control-plane \
     ctr --namespace k8s.io images inspect docker.io/library/cogniflow-kserve:qualification \
     | grep -F "@${KSERVE_IMAGE##*@}"
   docker exec cogniflow-module1-qualification-control-plane \
     ctr --namespace k8s.io images tag docker.io/library/cogniflow-kserve:qualification \
     "$KSERVE_IMAGE"
   docker exec cogniflow-module1-qualification-control-plane \
     crictl inspecti "$KSERVE_IMAGE"
   ```

   Kind imports the OCI index under the loaded tag rather than retaining its canonical digest
   name. Stop unless `ctr images inspect` shows the requested index digest before adding that
   digest alias, or unless `crictl inspecti` resolves the alias afterward. The alias does not
   replace the digest with the tag; both names point to the verified descriptor. Stop if
   BuildKit does not report one linux/amd64 manifest digest or the image cannot be loaded into
   the exact named cluster. The ten control-plane substitutions and their
   exact digests are the complete `rendered_images` map in
   `docs/module1/upstream-source-inventory.json`; changing any one requires new source
   review and authorization.

   Docker Buildx is a prerequisite for this exact image command. It was not installed on
   the reviewed host and must be supplied and version-recorded on the separately approved
   disposable host; do not replace the immutable-digest step with a tag-only build.
3. Authorize qualification separately, then run
   `qualification/module1/qualify.sh --execute --installation-evidence INSTALL_EVIDENCE_DIRECTORY
   --qualification-evidence NEW_QUALIFICATION_EVIDENCE_DIRECTORY`.
   The output directory must not exist. This preserves previous failed attempts and records
   the exact installation hashes and kind-containerd resolution of `KSERVE_IMAGE` before any
   qualification resource is created.
   It requires strict readiness, HTTP 200 prediction,
   metadata, internal service routing, observed 1→0→1 KPA behavior, cold activation and a
   successful post-cold prediction, then captures resources, RBAC and the live inventory.
4. Run `qualification/module1/negative-tests.sh` only against a reviewer-prepared
   qualified matrix copy and the captured snapshot. It proves version, image, CRD,
   autoscaling and route drift fail closed.
5. Scan every captured image digest; record tool/database versions and raw reports.
6. After evidence is copied to an immutable review location, request a third, explicit
   authorization before deleting the exact disposable cluster. No supplied script deletes
   it. The reviewed cleanup command is
   `KUBECONFIG=INSTALL_EVIDENCE_DIRECTORY/kubeconfig kind delete cluster --name cogniflow-module1-qualification`.
   Preserve the evidence directory and its private kubeconfig until deletion is independently
   confirmed; deletion is not a recovery mechanism for a failed qualification. Do not commit
   generated model artifacts, kubeconfig credentials or other evidence secrets.

On any failure, stop issuing cluster commands, preserve the new evidence directory, record
the failing command and `install-result.json` or `qualification-result.json`, and request
review. Never rerun into the same directory. Recovery is either a reviewed continuation
against the exact private kubeconfig or separately authorized deletion followed by a new
evidence directory and a fresh installation authorization.

The installer preserves the pinned checkout, exact rendered YAML, SHA-256 files, resource
identity inventory and logs. It separately preserves the raw upstream renders, pins the ten
required mutable source tags to reviewed linux/amd64 manifest digests, and records the exact
removal of the disabled kernel-cache DaemonSet. Its published tag is inaccessible and kernel
cache is disabled and unnecessary for CogniFlow inference. Runtime capture re-hashes the
applied artifacts, checks each
resource identity exists, records actual Pod `imageID` digests, verifies all workloads and
CRDs are ready, and reads effective Knative autoscaler/default timeout ConfigMaps. The
in-cluster provenance ConfigMap is corroborating metadata only, not independent proof.

Only an independent human reviewer may copy accepted digests/charts/CRDs into
`approved_inventory`, set the selected candidate suitable/qualified, and change the matrix
to `QUALIFIED`. Upstream CI alone cannot authorize that change.

## Authorized recovery from installation-order failures

Pinned Istio contains `Sidecar` resources `ml-pipeline-ui-exception` and
`notebook-controller-exception` in namespace `kubeflow`. The pinned upstream installation
order creates `common/kubeflow-namespace/base` first; its immutable render contains the
`kubeflow` and `kubeflow-system` namespaces plus their NetworkPolicies. Fresh installation
now preserves that raw render, inventories every identity, and applies it before cert-manager
and Istio. The controller, CRD and seven-policy expectations do not change.

The pinned Knative render also contains both CRDs and their dependent
`Image/queue-proxy` and `Certificate/routing-serving-certs` resources. The KServe render
similarly combines its CRDs with `ClusterServingRuntime` and `ClusterStorageContainer`
resources. Installation and recovery split only the prepared render for application: they
record the original and derived SHA-256 hashes and identities, apply CRDs first, wait for
`Established`, verify the required served version and API discovery, and only then apply the
remaining resources. The immutable prepared manifests and approved inventory remain unchanged.

For the existing partially installed disposable cluster, do not rerun `install.sh` and do
not alter the original evidence directory. After separate recovery authorization, run from
the reviewed repair commit with a new absolute evidence directory:

```bash
qualification/module1/recover-istio.sh --execute \
  --original-evidence /absolute/path/to/the/failed-install-evidence \
  --recovery-evidence /absolute/path/to/a/new-recovery-evidence-directory
```

The recovery verifies the original manifest hashes and pinned checkout, copies the original
raw renders into new evidence, adds the exact upstream namespace render, reruns digest and
inventory checks, captures pre-recovery resources, and applies the complete sequence with
idempotent Kubernetes apply operations. Each staged application records its own manifest
hashes, identities and PASS/FAIL result below `apply-stages/`. `set -euo pipefail` and the
`ERR` trap stop on the first failed apply and retain `recovery.log` plus
`recovery-result.json`. Each attempt must use a new recovery evidence directory; the original
installation and every failed recovery directory remain unchanged.

After a successful recovery, the still-separate qualification authorization uses the new
recovery evidence directory. Cluster deletion remains a third operation and is never called
by the installer, recovery, or qualification scripts.
