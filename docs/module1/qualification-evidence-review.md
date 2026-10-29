# Module I local qualification evidence review

This packet indexes and reviews the preserved local kind qualification at
`/var/tmp/cogniflow-module1-qualification-final-retry-20261028T050352Z`.
It accepts no production model, release, compatibility matrix or cloud target.

## Provenance and integrity

The directory contains 22 original files collected on 2026-10-28 from
00:03:53 through 00:07:36 America/Chicago. The complete file-level SHA-256
ledger is [`qualification-evidence.sha256`](qualification-evidence.sha256).
The ledger was created after collection; it proves the bytes reviewed now, not
that the files were signed, timestamped by a trusted service or immutable since
collection. `installation-evidence.sha256` independently verifies the referenced
installation record and rendered-manifest ledger, but does not cover all 22
qualification files.

The raw packet is intentionally not copied into Git. It contains local absolute
paths, Kubernetes object UIDs/resource versions and operational metadata that
are unnecessary for repository review. The checked-in ledger and this summary
contain no credential, kubeconfig, token or private key.

## Verified observations

| Observation | Preserved source |
|---|---|
| Kubernetes 1.34.11; KServe 0.21.0; Knative Serving 1.23.0; Istio 1.31.3; cert-manager 1.21.2 | `kubectl-version.json`, `runtime-snapshot.json` |
| 15 required controller workloads available | `runtime-snapshot.json` |
| 16 distinct controller container image references resolved to `@sha256` | `runtime-snapshot.json` |
| 38 required CRD names captured | `runtime-snapshot.json` |
| Predictor image `docker.io/library/cogniflow-kserve@sha256:75c140d0…9d6` | `inferenceservice.yaml`, running resources |
| Cluster-local namespace, labels, service URL and route readiness | `inferenceservice.yaml`, `knative-service.json`, `runtime-snapshot.json` |
| Initial ready replicas 2, exact zero, cold-ready replicas 2, post-inference replicas 2 | `scale-observations.jsonl` |
| Desired replicas zero with observed generation current; zero matching serving Pods | `zero-deployment.json`, `zero-pods.json` |
| Current ready revision received 100% traffic | `knative-service.json` |
| Cold activation 24 seconds within the 35-second deadline | `cold-readiness-observations.jsonl`, `qualification-result.json` |
| Initial, cold and post-cold prediction bodies were successful and identical | `prediction.json`, `cold-prediction.json`, `post-activation-prediction.json` |

The evidence files preserve response bodies rather than HTTP status lines. The
qualification script only writes each response after `curl --fail-with-body`
succeeds, so HTTP 200 is an assertion supported by the reviewed collector and
responses, not a status code independently embedded in the packet.

The executable autoscaling contract is **positive → exact zero → positive**.
The preserved observation is **2 → 0 → 2**. KPA target concurrency `1` is not
an assertion that exactly one replica must run.

## Security review

- The predictor runs as UID 10001, non-root, without privilege escalation, with
  all Linux capabilities dropped, a read-only root filesystem, RuntimeDefault
  seccomp, bounded CPU/memory and a 64 MiB `/tmp` volume.
- The qualification client uses a dedicated ServiceAccount and Pod with token
  automount disabled, a digest-pinned image, Restricted-style security context
  and bounded resources. Its recorded permissions contain discovery and
  self-review only, not application resource mutation.
- Gateway ingress is restricted to the labeled qualification client in the
  qualification namespace on TCP 8081. The model route is cluster-local.
- All 16 controller image references and the predictor image are immutable
  digests. No preserved Trivy/OSV result, SBOM or signature covers those exact
  runtime digests; this packet therefore makes no vulnerability-free or signed
  release claim.
- The pinned Istio CNI requires host CNI, proc, network namespace and runtime
  paths. That privileged node boundary remains subject to independent review.
- Seven broad upstream Istio AuthorizationPolicies remain an explicit human
  acceptance item. No allow-all policy was added to the predictor namespace.
- The recorded `GHSA-v824-8gxh-pgjw` disposition is limited to this minimal
  qualification topology: Kubeflow profile/editor roles were not installed and
  the model ServiceAccount received no RoleBinding. It is not a general
  production mitigation.

At review time, Trivy, Syft, Grype and Cosign were not installed, and the
qualification image was not available in local Docker by its immutable digest.
Docker 29.9.1, Helm 4.3.0 and jq were available. No image was pulled and no new
scan or SBOM evidence was generated.

## Synthetic model disclosure

The runtime used `qualification-model` version `1`, source
`local://disposable-qualification`, zero Git revision, synthetic-proxy labels
and approver identity `disposable-qualification-only`. Its approval-shaped
metadata authorizes only the disposable fixture. It is not the registered
Module I model, independent model approval or production promotion.

## Known limitations

- Local kind evidence does not establish GKE compatibility or cloud readiness.
- The compatibility matrix remains `BLOCKED`; no candidate or inventory is
  approved by this packet.
- No exact-digest vulnerability scan, SBOM, image signature or attestation is
  preserved.
- The original 22 files lack a contemporaneous complete signed checksum set.
- Eight offline mutation tests freshly rejected Kubernetes patch, component
  version, mutable image, missing CRD, manifest hash, autoscaler configuration,
  route and cold-deadline drift. They validate the current validator against
  temporary copied JSON, not historical runtime failures from the cluster.
- No genuine approved Module I model, FastAPI HPA, public TLS/authentication,
  hosted observability, GCS registry round trip, rollback or teardown is proven.
- The repository's course rubric is an owner-maintained mapping; the original
  two-page instructor document is not present for independent transcription review.

## Recommendation and decision

Recommendation: accept the packet as evidence that the stated synthetic model
completed the reviewed local kind KServe/Knative contract, including scale to
zero and bounded cold activation. Do not use it to qualify GKE, approve a model,
approve images or unblock the production compatibility matrix.

Independent reviewer: **PENDING**

Decision: **PENDING — ACCEPT LOCAL KIND / REJECT / NEEDS MORE EVIDENCE**

Reviewer identity and affiliation:

Decision timestamp (UTC):

Reviewed commit and ledger SHA-256:

Rationale and exceptions:
