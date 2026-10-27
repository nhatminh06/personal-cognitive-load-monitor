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
   `kind-cogniflow-module1-qualification`.
2. Generate `build/model-package` with
   `PYTHONPATH=src uv run python scripts/generate_qualification_model.py build/model-package`; build the
   KServe image locally, load it into kind or a disposable loopback registry, and set
   `KSERVE_IMAGE` to its immutable digest. Do not publish it.
3. Authorize qualification separately, then run
   `qualification/module1/qualify.sh --execute --evidence-dir INSTALL_EVIDENCE_DIRECTORY`.
   It requires strict readiness, HTTP 200 prediction,
   metadata, internal service routing, observed 1→0→1 KPA behavior, cold activation and a
   successful post-cold prediction, then captures resources, RBAC and the live inventory.
4. Run `qualification/module1/negative-tests.sh` only against a reviewer-prepared
   qualified matrix copy and the captured snapshot. It proves version, image, CRD,
   autoscaling and route drift fail closed.
5. Scan every captured image digest; record tool/database versions and raw reports.
6. After evidence is copied to an immutable review location, request a third, explicit
   authorization before deleting the exact disposable cluster. No supplied script deletes
   it. Do not commit generated model artifacts or credentials.

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
