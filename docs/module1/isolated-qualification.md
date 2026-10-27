# Module I isolated KServe qualification

Status: **BLOCKED**. No disposable cluster qualification was run and no candidate is `QUALIFIED`.

## Immutable upstream candidate

The candidate is Kubeflow Community Distribution commit
[`f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0`](https://github.com/kubeflow/community-distribution/tree/f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0),
not mutable `master`. Its manifests declare KServe 0.21.0, Knative Serving 1.23.0,
Istio 1.31.3 and cert-manager 1.21.2. The disposable cluster is separately pinned to
Kubernetes 1.34.11 by the kind node image digest in `qualification/module1/install.sh`.

The pinned source contains Kustomize installations plus Helm sources for cert-manager,
Knative and KServe. Qualification inventory must include all three KServe controllers,
six Knative/net-istio controllers, Istiod, all three cert-manager controllers, the three
required serving CRDs, chart/source versions, and runtime-resolved image digests. The
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
cluster. The high-severity
[`GHSA-v824-8gxh-pgjw`](https://github.com/kubeflow/community-distribution/security/advisories/GHSA-v824-8gxh-pgjw)
depends on Kubeflow editor/profile permissions to create Istio routing resources. This
minimal procedure installs neither those roles nor profiles, and its qualification service
account receives no RoleBinding. The captured `kubectl auth can-i --list` output must
confirm that boundary. Before production review, attach Trivy/OSV results for every
runtime-resolved digest.

## Authorized run sequence

Do not run these commands against an existing context. A reviewer must authorize the
disposable run, verify the context name after installation, and then:

1. Run `qualification/module1/install.sh`.
2. Generate `build/model-package` with
   `PYTHONPATH=src uv run python scripts/generate_qualification_model.py build/model-package`; build the
   KServe image locally, load it into kind or a disposable loopback registry, and set
   `KSERVE_IMAGE` to its immutable digest. Do not publish it.
3. Run `qualification/module1/qualify.sh`. It requires strict readiness, prediction,
   metadata, internal service routing, observed 1→0→1 KPA behavior, cold activation and a
   successful post-cold prediction, then captures resources, RBAC and the live inventory.
4. Run `qualification/module1/negative-tests.sh` only against a reviewer-prepared
   qualified matrix copy and the captured snapshot. It proves version, image, CRD,
   autoscaling and route drift fail closed.
5. Scan every captured image digest; record tool/database versions and raw reports.
6. Delete the disposable kind cluster after evidence is copied to an immutable review
   location. Do not commit generated model artifacts or credentials.

Only an independent human reviewer may copy accepted digests/charts/CRDs into
`approved_inventory`, set the selected candidate suitable/qualified, and change the matrix
to `QUALIFIED`. Upstream CI alone cannot authorize that change.
