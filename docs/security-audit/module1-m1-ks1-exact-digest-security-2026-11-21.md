# M1-KS1 — exact-digest KServe security qualification (2026-11-21)

**Decision: BLOCKED.** Every one of the 17 required upstream Linux/amd64 image manifests has HIGH findings; four have CRITICAL findings. The two CogniFlow application images pass fresh local scans, but neither selected deployment image has a published immutable OCI digest. This is an offline image-security assessment only. No Kubernetes workload, cloud resource, or serving model was run.

## A. Repository and security baseline

- Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. The pre-existing dirty working tree was preserved. No source, deployment, or compatibility policy was changed for this milestone.
- The proposed upstream source is pinned at Git commit `f121d4bdf99e0afa87ecaf3a06289a03a73f3ee0` under `/var/tmp/cogniflow-module1-install-20261120T202252Z/upstream`. The compatibility matrix remains `BLOCKED`, with `selected_candidate: null`. Its candidate versions are KServe 0.21.0, Knative 1.23.0, Istio 1.31.3, and cert-manager 1.21.2.
- C5.3 reported 0 HIGH/0 CRITICAL for two **local** application image IDs. That historical result does not qualify registry artifacts or the current local IDs. Existing Module I Kubernetes/GCP runtime and production status remain NOT QUALIFIED/NOT READY.
- Preflight: 12 logical CPUs, 15 GiB RAM (8.4 GiB available), 142 GiB free disk. Trivy 0.76.2; vulnerability DB v2 updated 2026-11-21 01:10:48 UTC, Java DB v1 updated 00:58:42 UTC. See `trivy-version.txt` and both DB metadata files.

## B. Required deployment image inventory

The verified rendered path has 16 controller/gateway workload objects, 38 CRDs, 16 distinct directly referenced upstream images and one dynamically injected Knative queue proxy image. Its 17 upstream image manifests plus two application images form the required inventory. The table records the exact Linux/amd64 OCI manifest selected by each pinned source reference; full repository names, configured tags/root digests, workloads, source manifests, and manifest responses are in `deployment-image-inventory.json`, `inventory.json`, and `manifests/`. Root index digests and child platform digests differ for some Knative images.

| Component / configured reference | Linux/amd64 manifest digest | HIGH | CRITICAL |
|---|---|---:|---:|
| cert-manager-controller (`quay.io/jetstack/cert-manager-controller:v1.21.2`) | `sha256:57bb397c639e0e94184ba67848e5dad04284f24645e521e764a0ee5f5002f286` | 7 | 0 |
| cert-manager-cainjector (`quay.io/jetstack/cert-manager-cainjector:v1.21.2`) | `sha256:aa2bc58725d92a643f5069dde58abc93b65566ded8951348873ac9ee7efef66c` | 6 | 0 |
| cert-manager-webhook (`quay.io/jetstack/cert-manager-webhook:v1.21.2`) | `sha256:b929259301ee75270ab4651d5e6bd4ba7b6624b1ce48ba767d064295a9312101` | 6 | 0 |
| proxyv2 (`docker.io/istio/proxyv2:1.31.3`) | `sha256:be401d180020fd4dba0d106135e1af1fb8f3796868c581068081a18c94c2534c` | 9 | 0 |
| pilot (`docker.io/istio/pilot:1.31.3`) | `sha256:1a349da3d48a59f2663256b50284de6ff84776db5ea9f42d426f752b34b44e62` | 9 | 0 |
| install-cni (`docker.io/istio/install-cni:1.31.3`) | `sha256:115d9d77a6f70da7ea84f997964e871bf4c9b0f235e56aed30c773ffd7154b06` | 14 | 0 |
| knative-serving/activator (`gcr.io/knative-releases/knative.dev/serving/cmd/activator@sha256:e5ab46f3b73fa2e3898fe47f6a3a0c2bd765596f4fb36ceb4c28c35d0a74b2e5`) | `sha256:fa1d1bd8108a50b1c3314e94e6e4079ce146626868669c68c799f463f8c7b173` | 17 | 0 |
| knative-serving/autoscaler (`gcr.io/knative-releases/knative.dev/serving/cmd/autoscaler@sha256:879da127b23db65d862cafa6b23fb987381d0e44150f0027d44e1f5aee83bde2`) | `sha256:c905ef6e6cd3ff3871bcd0c480d11b760616dca1d9ed2c4c08d1b0e6e3cfc7c8` | 17 | 0 |
| knative-serving/controller (`gcr.io/knative-releases/knative.dev/serving/cmd/controller@sha256:ca5062ece0329d002a81940cf4268d7898866434d70049bb93f27d3a786d3292`) | `sha256:a63cc1a6c74fe4d6ff3e8958141dac1e988c693a4726e1d6358a301b4ee8c9b1` | 19 | 0 |
| knative-serving/net-istio-controller (`gcr.io/knative-releases/knative.dev/net-istio/cmd/controller@sha256:cf1530d3b625d247114f006e4902ba8c0f2a3196d1d7a6b7acbeb7d7db11d148`) | `sha256:55553554c70b51dc07d4fef84b2267035d470a5ce38a87e23a640248f3ae62b4` | 17 | 0 |
| knative-serving/net-istio-webhook (`gcr.io/knative-releases/knative.dev/net-istio/cmd/webhook@sha256:ac5c0458f32e353a635919ccd89fe77a7bf650c5354dd76c71e9316eff5de65d`) | `sha256:40be3470b4aa4e9df7cd0fa08c98f28a02c476661c94b323f775075401edc72b` | 17 | 0 |
| knative-serving/webhook (`gcr.io/knative-releases/knative.dev/serving/cmd/webhook@sha256:3846e9a416665c5b9ec2e4de246cfcb5c4ab0d01ba19348aa008caf30144b650`) | `sha256:6fa9f4e7617ae631562023d24deedf065dbe027ae321d8c6fee4125927020bca` | 17 | 0 |
| kserve-controller (`kserve/kserve-controller:v0.21.0`) | `sha256:878cb1a071a378b25da91c2d74c03d88e288dbbcdaf7cb87c776dcc849fcdf5f` | 14 | 1 |
| kube-rbac-proxy (`quay.io/brancz/kube-rbac-proxy:v0.18.0`) | `sha256:62eeb8a0aaa13a8d886de07e5805940cec079ffbaf1d74483e26ad4a84952dce` | 55 | 2 |
| kserve-localmodel-controller (`kserve/kserve-localmodel-controller:v0.21.0`) | `sha256:ef525ebc445e1fe6108c4c013d819620e5d80e1450539fb54ff65ace0c959a83` | 14 | 1 |
| llmisvc-controller (`kserve/llmisvc-controller:v0.21.0`) | `sha256:e3d71368f622e8c57a088de15e23c28f981c6c51b4b028cb1b1081f0c472adf1` | 14 | 1 |
| dynamically injected into Knative Revisions (`gcr.io/knative-releases/knative.dev/serving/cmd/queue@sha256:a3cc71ce80dbc6df8781f15eac2cf3531a4c9815271799afd8776bef9e6aeaf2`) | `sha256:ade30a5e4c96e903e5ef8a8754944ea67ee2123ede59a508e2748a81748c9bbb` | 17 | 0 |

The application Deployment and InferenceService predictor in `helm/cognitive-load-monitor/values.gke.yaml` use `SET_PROJECT` and zero-digest placeholders. Their exact published Linux/amd64 manifest digests, registry provenance, signatures and SBOM attestations are unavailable. No local Docker image ID is treated as a registry digest.

| Application | C5.3 scanned local ID | Current local ID (fresh scan) | Current H/C |
|---|---|---|---:|
| CogniFlow FastAPI | `sha256:9609981bd9c775b3937a0d8cf7158c02e786089cd35ce1de5352d90b4ace26c0` | `sha256:7be6396c4be5ebcb546091234fe547426588fbcc92b4d49de16327028680e0bd` | 0/0 |
| CogniFlow KServe predictor | `sha256:6e4a0d3c3682fec3c85e3676acb268d422819f5378494f3b26e78ad99cba3f9b` | `sha256:ff13df8076ede18ae270b7009f542684ec9c46a75450bd2db678f26b5f6cdea0` | 0/0 |

## C. Local ID versus OCI digest reconciliation

The C5.3 application IDs differ from the images currently carrying the local tags. Fresh scans of the current IDs are 0/0, but there is no exact published OCI manifest selected for the intended deployment. Local `RepoDigests` reflected local image IDs and were not accepted as registry manifest provenance. All 17 upstream platform digests were resolved from the pinned source references; `docker buildx imagetools` handled two manifest formats the Docker CLI could not parse. No image was started or loaded into a local runtime.

## D. Existing evidence verification

The preserved rendered-manifest `sha256sum -c` check passed, and seven fresh offline `kubectl kustomize` renders matched the corresponding preserved raw renders byte-for-byte (`kustomize-validation.json`). C5.3 report IDs and 0/0 counts were reconciled with current local IDs, but the historical C5.3 raw JSON was not independently revalidated in this milestone; current local images were rescanned because their IDs changed. The previous source inventory omitted the Knative queue-proxy injection; this assessment includes it. No previous upstream exact-image scan was promoted to a fresh pass.

## E. Fresh exact-image scan results

All 17 upstream images and both current local application images were scanned with Trivy 0.76.2 against the recorded fresh DB. Commands used `trivy image --image-src remote --platform linux/amd64 --skip-db-update --skip-java-db-update --offline-scan --scanners vuln --format json` for upstream manifests (the current local app IDs used Docker source). No severity filtering, CVE ignore, or scan exception was used. `scan.py`, `scan.log`, `reports/*.json`, and `scan-summary.json` retain command implementation, raw results, logs and completion status. `package-inventory.tsv` contains detected packages/targets; no separate SBOM was generated.

The 17 upstream images have **269 HIGH and 5 CRITICAL finding occurrences**, across 63 distinct advisories. Every upstream image fails the 0/0 gate. Both current local application images have 0/0, with Wolfi OS and Python dependency scan targets; these results qualify only those local IDs. Full per-image OS/language targets and all severity counts are in `scan-summary.json`.

## F. Vulnerability root-cause analysis

Of 274 upstream HIGH/CRITICAL occurrences, 265 are in Go binaries and 9 in Ubuntu OS packages. The most repeated affected packages are Go `stdlib` (135), `golang.org/x/net` (41), `google.golang.org/grpc` (27), `golang.org/x/crypto` (17), `istio.io/istio` (16), and `golang.org/x/text` (15). The Ubuntu findings affect Istio proxy, pilot and CNI images. No Java or Python vulnerability target was reported for these upstream controllers. The complete per-image package, advisory, installed version, fixed version and source URL inventory is `high-critical-vulnerabilities.tsv`; `all-vulnerabilities.tsv` includes lower severities. Embedded Go dependencies belong to upstream-built controller binaries; replacing OS packages alone cannot clear this gate.

| Critical advisory | Affected upstream component(s) | Installed → Trivy-reported fixed version |
|---|---|---|
| CVE-2025-68121 / `stdlib` | kube-rbac-proxy | `v1.22.4` → `1.24.13, 1.25.7, 1.26.0-rc.3` |
| CVE-2026-33186 / `google.golang.org/grpc` | kube-rbac-proxy | `v1.64.0` → `1.79.3` |
| CVE-2026-77524 / `github.com/kedacore/keda/v2` | kserve-controller, kserve-localmodel-controller, llmisvc-controller | `v2.20.2` → `2.21.0` |

Trivy lists fixed package versions for the reported H/C rows. Those versions do **not** establish that a vendor-supported, mutually compatible replacement controller stack exists. No dependency overrides, patched forks, image rebuilds, or substitutions were attempted. Each vendor must publish coherent remediated images, including rebuilt Go binaries, before rescanning.

## G. Missing and indirect image coverage

The Knative queue-proxy is dynamically injected from the serving configuration and was scanned. Istio sidecar injection is admission-time behavior: the gateway `proxyv2` manifest was scanned, but the actual admitted pod sidecar digest cannot be proven offline. KServe storage-initializer and agent references are conditional and are not selected by the current custom predictor without `storageUri`; if enabled, their mutable tags need separate digest resolution and scans. Local-model node/kernel agents and web UI remain deliberately omitted. The qualification curl client is test-only. See `deployment-image-inventory.json`.

## H. Offline security configuration checks

`helm lint` passed and the synthetic Helm render produced nine documents. App containers specify non-root UID 10001, RuntimeDefault seccomp, read-only root filesystem, disabled privilege escalation, dropped capabilities and resource limits. Upstream render review found 16 workloads and 38 CRDs; several upstream controllers have no explicit resource limits, many service-account token mounts remain implicit, and seccomp/read-only-root settings vary. Istio CNI has `runAsNonRoot: false`, NET_ADMIN/NET_RAW/SYS_PTRACE/SYS_ADMIN/DAC_OVERRIDE capabilities and hostPath mounts for CNI/network namespace paths. Seven upstream allow-all NetworkPolicies were inventoried. The assessment does not assert whole-stack Pod Security compliance or validated RBAC/network isolation. The synthetic render uses fake digest placeholders solely for offline checks; no Kubernetes API was contacted. Details are in `offline-workload-security.json` and `helm-resource-summary.json`.

## I. Artifact provenance and signing gaps

The upstream Git source commit, rendered-manifest checksums and registry platform manifests are recorded. Signatures, publisher attestations and protected release workflow provenance were not verified; `cosign` was unavailable. The application images have no real published manifest digest, signing, build provenance or SBOM attestation in the selected deployment values. Local vulnerability qualification, published exact-digest qualification, and Kubernetes runtime qualification remain separate gates. No registry write, publication or signing occurred.

## J. Compatibility and regression checks

- Focused Module I qualification, compatibility, acceptance, Helm guard, KServe manifest, qualification-client and gateway tests: **102 passed**.
- `helm lint helm/cognitive-load-monitor`: **1 chart linted, 0 failed**. Offline Helm synthetic render: **9 documents**. Seven Kustomize renders matched preserved raw output; rendered checksums passed.
- `.venv/bin/ruff check src scripts jobs dags pipelines`: **PASS**. `git diff --check`: **PASS**. The compatibility matrix script completed successfully while the matrix itself stayed `BLOCKED` / no selected candidate.
- No runtime compatibility, model inference, Kubernetes admission, CNI operation, image pull or cloud deployment was tested. No source or policy change justified a full regression run.

## K. Resource usage and cleanup

Scans used task-owned `build/security-scans/module1-kserve-exact-digest-2026-11-21/` cache and remote registry reads; no image was executed, no Docker container/volume/cluster was created or changed. The 3.2 GiB task-owned scan cache was removed after preserving raw reports and DB metadata. At closeout: 8.9 GiB host RAM available and 142 GiB disk free. A final Docker socket read returned permission denied, so a post-scan container count was not independently verified; no Docker-mutating command was run. Existing shared Docker caches and evidence were untouched.

## L. Remaining blockers

1. Every required upstream controller/gateway/queue image fails the 0 HIGH / 0 CRITICAL gate; KServe controllers and RBAC proxy include CRITICAL findings.
2. CogniFlow application deployment refs lack real published manifest digests and signatures/provenance, despite passing current local-ID scans.
3. Dynamically admitted sidecar identity, conditional images if enabled, whole-stack security context, RBAC and network controls need runtime-stage verification after security clearance.
4. The compatibility matrix has no selected, qualified KServe candidate. Kubernetes/GCP runtime and production remain unqualified; Module II Spark remains blocked independently.

## M. Recommended next milestone

Obtain vendor-supported coherent patched versions for KServe, Knative, Istio and cert-manager, including rebuilt Go binaries and a security-cleared RBAC proxy; verify their supported version matrix and upstream provenance. Resolve every configured and injected Linux/amd64 manifest digest, then rerun fresh full OS/language scans with zero HIGH/CRITICAL and retain checksums. Publish and attest the two application images only under a separately authorized protected release workflow, then verify exact published digests. Only after the image gate passes should a separate isolated Kubernetes compatibility and runtime qualification be proposed. Do not turn on conditional components without adding them to the exact-image inventory.

## N. Final qualification decision

**BLOCKED.** Required upstream images fail the existing security gate. The milestone does not authorize KServe deployment, Kubernetes/GCP execution, model approval or production release. Module II independent passes remain limited to their recorded scopes; Spark and full Module II integration remain unqualified.

### Retained evidence

All raw scan JSON, logs, package/vulnerability inventories, image manifests, offline render, tool/DB metadata, inventory, and source scripts are retained under `build/security-scans/module1-kserve-exact-digest-2026-11-21/`. `SHA256SUMS` covers retained files and was checked with `sha256sum -c`. The evidence directory is ignored by Git; this report is the only new tracked-path file from the milestone.
