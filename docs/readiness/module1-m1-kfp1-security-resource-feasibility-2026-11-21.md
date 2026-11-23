# M1-KFP1 — KFP security and resource feasibility gate (2026-11-21)

## A. Executive summary

**NO-GO for isolated Kubernetes qualification. Recommended action: DEFER_KFP.** The selected KFP 2.18.1 / Argo 4.1.6 headless stack has substantial local image and component evidence, but the release identity is unpublished/unsigned, the current headless image ledger does not match its MLflow patch, the C11 acceptance gate is still incomplete, and current host available RAM is below its 12 GiB threshold. The MLMD invalid-credential SIGSEGV remains unresolved. No Kubernetes or Docker runtime was used in this assessment.

## B. Repository baseline

Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. Pre-existing modified and untracked files were preserved. Reviewed `AGENTS.md`, [CF-R1](cogniflow-cross-module-readiness-2026-11-21.md), C14–C23 reports and tracked assessment JSON, [C11 plan](../../deploy/c11/preflight-plan.json), [C11 controller matrix](../../deploy/c11/controller-compatibility.json), the [M1-KS1 result](../security-audit/module1-m1-ks1-exact-digest-security-2026-11-21.md), the current overlay, release ledger, compiled pipeline and acceptance scripts. C11 describes a broader cross-module gate; its old PostgreSQL, unqualified MLflow/storage and metadata-image entries are stale for this headless path. Its explicit target, controller and publication gates remain binding if that acceptance path is used.

## C. Current version and component inventory

- Selected local source: KFP **2.18.1** at upstream commit `7dd28116ad652bfb7b6c282e7920be84e6a7634a`, Argo Workflows **4.1.6**, SDK and `kfp-kubernetes` **2.17.3**, MySQL **8.4.13**, MLMD **1.14**, SeaweedFS **4.54**, MLflow **3.17.2** in the locally tested C20 path. Kubernetes **1.35.x** is proposed in C11, but its exact kind node identity is unqualified. These are selected/proposed versions, not a tested combined cluster.
- C22 retained an offline headless render of **73 objects and 16 container/init-container image uses**, all digest shaped, with 73/73 structural OpenAPI checks. The overlay deletes caching, UI, viewer and visualization Deployments and the UI signing-key Job. Those services are optional for the cache-disabled six-step graph. C22 did not execute the overlay.
- The mandatory role set is the 15 entries in `deploy/releases/kfp-local-images.json`: KFP API, persistence agent, scheduled workflow, workflow controller/executor, KFP driver/launcher, metadata Envoy/writer, wait/init helper, MySQL, MLMD, SeaweedFS, MLflow and training component. A repeated image use explains why 16 render uses do not imply 16 distinct role IDs. The exact workload/CRD/PVC mapping of the retained 73-object render cannot be independently enumerated today because the render file is not retained here and the Kustomize base is a remote Git reference; this milestone did not fetch it.

### Local role identities (not published OCI manifest digests)

| Role | Exact local ID in release ledger | Latest attributable local status |
|---|---|---|
| kfp-api | `sha256:d70accf415ef407fd23fd7a790cfd8f9ec9877324018434264fdb66d378859ad` | C16 0/0; non-root 65532 |
| persistence-agent | `sha256:707c3af5abdb6c57902036916fd0d74d6bb014889a30c19e16574a71c92a68dc` | C16 0/0; non-root 65532 |
| scheduled-workflow | `sha256:9fa52c2f7e8a6eb62df0e38afec42be1d44cd15ffd85cd3942b2910455d491f3` | C16 0/0; non-root 65532 |
| workflow-controller | `sha256:c115303d506de611f4d230c1a3f234eb7b1feae153c755a79dad56ebb91b44fd` | C16 0/0; non-root 8737 |
| workflow-executor | `sha256:f597b17060742da11004bd5badc1a401cb65125035fcdb1f6550c802a4515802` | C16 0/0; non-root 8737 |
| kfp-driver | `sha256:175b9bbf02a4fde6211a6716dc499524236729b30dd75e6cd2362fc25480f963` | C16 0/0; non-root 65532 |
| kfp-launcher | `sha256:8e2f3860b0853bd841c8fc86113f5fe3d9964f7e87ebf693cd064abfd57ad9c5` | C16 0/0; non-root 65532 |
| metadata-envoy | `sha256:bf7ad93d1c0621f0081e1c2f5be1e96b6955b2615115564837f88b3e95c33126` | C19 0/0 |
| init-helper | `sha256:469c9ea410b9215eaee7976ba6c0639039b444be8e5d638f7abbada189971eb2` | C19 0/0 |
| mysql | `sha256:febda51c2aa5e451cb2d4161f1c82f731dc5e36cbf06be80eea4ed17e9dcb5e6` | local ID is in active patch; C18 qualifies an *older*, different ID |
| mlflow-gcs | `sha256:a9741a4d3248444027c0f605114024e2294e25504cde7b5def31c18694f445f5` | ledger says 0/0 local; active overlay uses different C20-qualified ID |
| seaweedfs | `sha256:4b42c212543a0acd4c0e675215ecdcaf62a186ef98def76c7e12701871222d15` | C19 0/0; local readback/restart |
| mlmd | `sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876` | C21 0/0; non-root 10001; negative-auth crash |
| metadata-writer | `sha256:c2a8d2322156040087818323c1e5d1e685dbb63142f52bad263512fb00fa2ae1` | C22 0/0; non-root 65532 |
| training-component | `sha256:e296269ccaa235661a1102c49bc98754f5a3d07e80c8c59e5e78d83a8cc2d1f9` | C23 0/0; non-root 65532 |

The rendered source patch uses MySQL `sha256:febda51c2aa5e451cb2d4161f1c82f731dc5e36cbf06be80eea4ed17e9dcb5e6` and MLflow `sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5`. The ledger uses the same MySQL ID but `mlflow-gcs` `sha256:a9741a4d3248444027c0f605114024e2294e25504cde7b5def31c18694f445f5`. C18’s MySQL assessment qualified `sha256:367c695a6870d1fed993457575846f13071ea3c8cee88d54a311251ff4dbf0f3`; no matching scan/SBOM report for the newer active MySQL ID was located. C20 records the active older MLflow ID at 0/0. The ledger and overlay therefore require identity-level reconciliation before any release decision.

## D. Exact-image security status

C16 reports seven controller/runtime IDs at 0 HIGH/0 CRITICAL with exact raw scan and SBOM SHA-256 values, covered OS and embedded language dependencies, and recorded non-root users. C19 adds SeaweedFS, metadata Envoy and init helper; C20 qualifies the active overlay MLflow ID; C21 qualifies MLMD; C22 qualifies metadata writer; C23 qualifies the training component. Assessment JSONs retain identities, source/build details and digest values. The actual C14–C23 raw scan/SBOM files were not located in the available task workspace, so their recorded hashes could not be independently recomputed here; this is reused historical local evidence, not fresh security verification. No image was pulled, built, executed or rescanned.

The current ledger’s newer MySQL ID is **UNVERIFIED against the available matching assessment**, and the newer `mlflow-gcs` ID has a 0/0 ledger entry and [evidence index](../evidence.md) but is not selected by the active overlay. No role has a verified, published registry manifest digest, signature, digest-bound SPDX/SLSA attestation or remote rescan. Local `sha256:` image/index IDs must not be promoted to published OCI manifests. Source commit/signature evidence in C14/C16 and local BuildKit attestations are useful provenance but do not close the remote release gate. Scanner data in the tracked local assessments is from Nov 19; no freshness claim is made for Nov 21.

## E. Superseded versus current findings

| Older finding | Current disposition |
|---|---|
| C16 PostgreSQL 18.7 image: 26 HIGH, 1 CRITICAL | Superseded for selected `platform-agnostic` MySQL overlay; do not apply it to current MySQL. |
| C16.3 failed/invalid MySQL candidate | C18 qualified a different Oracle Linux 9.8 MySQL 8.4.13 local ID; the currently patched newer MySQL ID still needs matching evidence. |
| C19 metadata writer 47 HIGH, MLflow 60 HIGH, unsupported MLMD OS | C20/C21/C22 locally qualified replacement MLflow, MLMD and writer IDs. The old images remain blocked and are not selected. |
| Old training component 60 HIGH | C23 replacement local ID passed 0/0 and six isolated commands. It has not run in Kubernetes. |
| C11 says artifact store/MLflow unselected, PostgreSQL blocker | Stale for the narrower C22 headless path; C11 still requires a complete remote release ledger and qualified controllers before its acceptance script can authorize a run. |
| CF-R1 says KServe exact images lack whole-image scans | M1-KS1 later scanned 17 upstream images: 269 HIGH and 5 CRITICAL occurrences, so the wider C11 controller matrix cannot pass. |

## F. Dependency and compatibility analysis

C14 records upstream KFP 2.18.1 CI coverage for Argo 4.1.6 and Kubernetes 1.33/1.36, but no present 1.35 cluster qualification. SDK 2.17.3 is a v2 client; local pipeline compilation proves syntax/source compatibility only. C18/C20/C21 show isolated MySQL, SeaweedFS, MLflow and MLMD behavior, including MLMD schema 10 and artifact readback, but never all together under the selected KFP/Argo controllers. The launcher points to SeaweedFS S3 with a referenced Secret; MLflow uses the MySQL backend Secret and S3 artifact destination. Missing live proofs include API/controller readiness, true KFP-issued run ID and terminal state, metadata writer lineage, MLflow candidate registration, restart persistence, authorization/negative cases and pipeline failure propagation. KServe is not required for this headless graph, but it remains required by the broader C11 cross-module matrix and is BLOCKED in M1-KS1.

## G. Resource and capacity ledger

The active patch files yield these **known** per-replica container resources; the remote KFP base supplies other workloads and PVCs, so this is a lower bound, not an exact 73-object total. Replica count 1 is explicit for MLflow; one replica for patched upstream Deployments is inferred from their prior rendered path and must be checked in the retained/full render. No init-container resource or PVC request can be certified from patches alone.

| Workload/container | Request CPU / RAM | Limit CPU / RAM | Replica certainty |
|---|---|---|---|
| MySQL | 100m / 512Mi | 1 / 1Gi | upstream base not independently rendered |
| MLMD gRPC | 25m / 64Mi | 500m / 256Mi | upstream base not independently rendered |
| Metadata Envoy | 50m / 64Mi | 250m / 256Mi | upstream base not independently rendered |
| Metadata writer | 25m / 128Mi | 500m / 512Mi | upstream base not independently rendered |
| Scheduled workflow | 50m / 128Mi | 250m / 256Mi | upstream base not independently rendered |
| MLflow | 100m / 512Mi | 1 / 2Gi | explicit 1 |
| Six sequential pipeline tasks (largest concurrent one) | 250m / 512Mi | 1 / 2Gi | source-level sequential graph |

Known patched-service lower-bound steady requests: **350m CPU / 1,408Mi RAM**; limits: **3.5 CPU / 4,352Mi RAM**. With one training task: at least **600m / 1,920Mi requested** and **4.5 CPU / 6,400Mi in configured limits**. These figures exclude API, persistence agent, workflow controller, SeaweedFS, driver/launcher/Argo run pods, init containers, replacements, system reserve and image cache. The single-node kind configuration reserves 250m CPU + 512Mi for the system and the same for kubelet (500m/1Gi total) and offers no single-node-loss tolerance. Replacement surge, complete steady/peak requests, maximum limits, PVC/storage-class requests and ephemeral-storage needs **cannot be computed defensibly** without the exact full render; missing requests may exist in the base. No observed runtime peak was inferred from limits. MLflow’s historical isolated maximum was 1.474 GiB, MySQL about 0.4–0.5 GiB, SeaweedFS 150–175 MiB; these are not combined-runtime measurements.

C11/C22 require **12 GiB MemAvailable** and **60 GiB free disk** for the isolated workflow. Current host `/proc/meminfo`: **9,381,101,568 bytes available (8.74 GiB)**, short by **3,503,800,320 bytes (3.26 GiB)**; installed RAM of 15.34 GiB does not satisfy the available-memory gate. Root disk has **151,421,251,584 bytes free (141.0 GiB)**, so the documented free-disk threshold passes, though image/PVC sizing remains unknown. Swap is not counted as available RAM. Current host therefore fails the resource gate before startup.

## H. Offline validation results

- Fresh compilation of source with C23 local component identity produced SHA-256 `966393bcacb604e09875f4dcd80c8430ee36fa2c9a253606d53567508f3268b4`, byte-identical to `pipelines/compiled/cogniflow-training.yaml`. Six executors use the same immutable, local-ID-shaped reference; each source task requests 250m/512Mi and limits 1 CPU/2Gi. This does not verify a published digest.
- Focused KFP pipeline, task, release inventory, C11 guard, C16 image, C18 MySQL, C20 MLflow and C21 metadata tests: **47 passed, 1 SQLAlchemy deprecation warning**. Python patches were not changed. `git diff --check` passed.
- Local overlay patch files were inspected for digest syntax, service accounts, Secrets, security contexts and resource values. The C22 retained 73-object render and structural validation are historical, not rerun. Fresh `kubectl kustomize` was deliberately skipped because `infra/kfp-local/kustomization.yaml` points to a remote Git base not present in a verified local checkout; fetching a mutable external input is outside this milestone. Consequently full CRD, PVC, init-container, RBAC, NetworkPolicy, namespace and missing-resource checks remain unverified. No Kubernetes API or kubeconfig was accessed.

## I. Known correctness risks

C21/C22 reproduce MLMD 1.14 invalid MySQL credentials as exit 139 / SIGSEGV after `mysql_real_connect` fails. The client was rejected, no tables were written, no test password leaked and OOM was false, but the crash is unresolved; restart policy only contains availability impact. It blocks the required graceful negative-auth/failure acceptance contract until a supported fix or a separately justified replacement is qualified. C23’s six component commands and candidate registration were isolated local tests; its deliberately non-KFP `pipeline_run_id` cannot prove KFP orchestration or MLMD publication. No authentic KFP run identity, failed run or recovery result exists for this selected stack.

## J. Publication and authorization gaps

No published/signed remote image set, digest-bound SBOM and provenance attestations, qualified remote scan, complete C11 image ledger or signed release overlay exists. `deploy/c11/preflight-plan.json` has `owner_authorization: false`, no qualified Cosign/Trivy paths, no image ledger and `storage_qualified: false`; `controller-compatibility.json` remains `BLOCKED`. The C11 script also requires KServe/Knative/ingress roles; M1-KS1 found mandatory KServe-stack image failures. An isolated-cluster target, explicit kubeconfig, reviewed Secrets and deployment/submission authorization are absent. These are separate from technical capacity; none was requested or used in this milestone.

## K. Blocking prerequisites

| Class | Component / evidence | Impact and smallest credible resolution |
|---|---|---|
| SECURITY | Current MySQL patch ID has no matching retained scan/SBOM assessment; published identities absent for all roles | Reconcile MySQL ID with source/build evidence, then qualify the exact deployment artifacts under the existing 0/0 gate and protected release workflow; registry publication needs explicit authorization. |
| DOCUMENTATION | MLflow GCS ledger ID differs from active C20 MLflow patch; full C22 render/raw C14–C23 scan files unavailable here | Select one exact MLflow artifact and preserve an attributable render/evidence manifest; avoid assuming two IDs are interchangeable. |
| COMPATIBILITY | KFP/Argo/SDK/MySQL/MLMD/MLflow/SeaweedFS were not jointly run; Kubernetes 1.35 node image is unqualified | After security/resource gates, use a separately authorized isolated run and prove all startup and acceptance contracts. |
| CORRECTNESS | MLMD invalid-credential SIGSEGV; no genuine KFP run/failure evidence | Obtain a supported fix and rerun negative credential test before claiming acceptance. |
| RESOURCE | 8.74 GiB available < 12 GiB required; full request/PVC/surge ledger unavailable | Free at least 3.26 GiB of **available** RAM without touching retained resources or use a larger isolated host; obtain exact cached full render and size every workload/PVC. |
| AUTHORIZATION | C11 plan false/incomplete; no cluster/publication/Secrets/submission approval | Owner authorizes a concrete reviewed release and isolated target only after technical prerequisites pass. |
| SECURITY / broader C11 | M1-KS1 KServe ecosystem 17/17 required upstream images fail 0/0 | Keep wider C11 gate blocked until vendor-supported exact images pass; do not conflate headless KFP with full Module I. |

## L. Recommended next engineering milestone

**DEFER_KFP** now. The smallest meaningful future engineering work is an **offline identity-and-capacity closure** when a supported, matching MySQL artifact and a verified local copy of the exact KFP 2.18.1 base/render are available: reconcile the MySQL and MLflow IDs, verify retained raw scans/SBOM hashes, enumerate all 73 objects/PVCs/init resources and calculate replacement surge. Separately obtain an upstream-supported MLMD negative-auth fix. Do not start a Kubernetes runtime or publish images until those concrete blockers, the 12 GiB host gate and the existing C11 security/authorization gates clear. This recommendation is a stop decision, not authorization for another run.

## M. Final decision

**DEFER_KFP — NO-GO.** Local image/component passes and byte-identical pipeline compilation are real but scoped. Exact published artifact security, complete resource scheduling, combined-runtime correctness and owner authorization are not established. KServe remains BLOCKED; Spark remains BLOCKED; cloud and production remain NOT QUALIFIED. No existing source/evidence was modified, and this report is the only file added by M1-KFP1.
