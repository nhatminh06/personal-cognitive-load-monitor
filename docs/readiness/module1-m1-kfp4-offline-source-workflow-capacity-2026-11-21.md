# M1-KFP4 — offline source closure and workflow capacity (2026-11-21)

**Decision: `PARTIAL`; recursive source rendering `PASS`; runtime suitability `UNVERIFIED`; 12Gi gate `FAIL`.** The exact KFP and Argo revisions were assembled into a fully local recursive source graph and the current M1-KFP3 overlay rendered successfully twice without network access. The result is byte-identical to the M1-KFP3 patched render. Workflow-source inspection recovered explicit KFP driver, importer and launcher budgets, correcting M1-KFP3's lower-bound accounting. Argo executor and workflow ephemeral-storage consumption remain unbounded and require runtime evidence. `DEFER_KFP` remains unchanged.

No M1-KFP3 source/configuration change was altered. M1-KFP4 adds only this report and ignored task evidence; no Docker, containerd, Kubernetes API, retained cluster, MLMD diagnostic/source, MySQL substitution, image operation, cloud operation, commit or push occurred.

## Gate summary

| Gate | Result | Basis |
|---|---|---|
| Exact KFP revision | **PASS** | KFP 2.18.1 source archive selects commit `7dd28116ad652bfb7b6c282e7920be84e6a7634a`; retained archive SHA-256 `4b50a172…59e55` matches C21/C22 evidence. |
| Exact Argo revision | **PASS** | KFP pins tag `v4.1.6`; retained C16 binds it to commit `43021573c5a35cbafae009043c132dfcef43a112`; fresh shallow checkout resolves the same commit and tree `8250441c…14eb5`. |
| Argo archive checksum | **FAIL** | Fresh GitHub commit/tag archives hash to `dd8b4513…2a04` and `e793bc7a…2645`, not retained C16 `94d75d93…eda7bb`. No equivalence is claimed. |
| Fresh Argo signature verification | **UNVERIFIED** | Commit carries RSA signature key `B5690EEEBB952194`, but the public key is unavailable locally. C16's prior verified result remains historical evidence only. |
| Recursive dependency closure | **PASS** | Temporary local KFP manifest copy replaces both Argo references traversed by the platform-agnostic overlay with paths into the exact checkout; no remote reference is traversed. Unused cluster-install references were also localized. |
| Recursive source render | **PASS** | Two direct offline Kustomize builds from KFP+Argo source completed successfully. |
| Repeat render | **PASS** | Both are byte-identical at SHA-256 `060e410a8240bd60acee65014baa6152d7e0793647a5ddc9e8c6cdbd172cf7a0`. |
| M1-KFP3 comparison | **PASS** | New recursive render and M1-KFP3 patched render are byte-identical: 73 objects, 10 Deployments, two PVCs, and the same resource/image configuration. Historical checksum equality was not forced; it occurred naturally. |
| Image-ledger consistency | **PASS** | Fourteen digest references occur in the render; every digest exists in the split role ledger. Local `mlflow-s3` is selected and `mlflow-gcs` is retained but not rendered. |
| Workflow configured accounting | **PARTIAL** | KFP driver/importer/launcher and main-task declarations are explicit; Argo executor resources and ephemeral storage are not. |
| Host 12Gi available-memory gate | **FAIL** | 11,527,148 KiB available = 11,257Mi, about 1,031Mi below 12Gi. No process or host setting was changed. |
| Runtime suitability | **UNVERIFIED** | Requires an authorized isolated runtime to measure executor, task, storage, controller and failure/retry peaks. |

## A. Source closure

### Exact revisions and trust boundary

The active KFP source is the recovered archive under `build/kfp-source-check.15ctzKrx/`, selected at commit `7dd28116ad652bfb7b6c282e7920be84e6a7634a`. Its archive checksum `4b50a172728854115776532673e0df6d98679fb8303a806d901bb7825e359e55` matches the C21/C22 records used by the current overlay.

KFP's Argo Kustomizations pin `v4.1.6` for the workflow controller, namespace RBAC and minimal CRDs. C16 independently records tag version 4.1.6, commit `43021573c5a35cbafae009043c132dfcef43a112`, a previously verified commit signature and archive SHA-256 `94d75d93774c8352417a74b465e13804da93875b1bfa29151a41a2ba31eda7bb`.

Fresh read-only upstream recovery resolved `v4.1.6` to that exact commit and Git tree `8250441c6b298fc99d990c04de167e2930414eb5`. This establishes Git identity. It does **not** reproduce the old archive bytes: GitHub's freshly generated commit and tag archives have different hashes, and a local `git archive` has a third hash. The old archive file is absent, so its hash cannot be reconstructed. Commit signature verification also cannot be independently repeated because key `B5690EEEBB952194` is not in the local keyring. These are separately reported `FAIL`/`UNVERIFIED`, not promoted from historical evidence.

### Local dependency graph and render

Task-owned `build/m1-kfp4-2026-11-21/` contains:

- the exact shallow Argo checkout and fresh archives;
- a copy of the recovered KFP manifests with remote Argo references rewritten only in that ignored copy;
- a copy of the current remediated overlay whose KFP base is the local manifest tree;
- two recursive-source renders, machine-readable results and checksums.

`kubectl kustomize` was used only as a client-side Kustomize v5.7.1 renderer; no Kubernetes API command or kubeconfig access occurred. Both renders completed offline and are identical to each other and to M1-KFP3. There are no semantic or resource-inventory differences to investigate.

## B. Workflow resource accounting

### Explicit and inherited resources

| Runtime element | Explicit requests | Explicit limits | Source / interpretation |
|---|---:|---:|---|
| Training main container | 250m / 512Mi | 1 CPU / 2Gi | Compiled pipeline; applies to each of six user components. |
| KFP component driver | 100m / 64Mi | 500m / 512Mi | KFP `argocompiler` `driverResources`; described upstream as empirical. |
| KFP importer | 100m / 64Mi | 500m / 512Mi | Importer uses `driverResources`; three independent importers exist. |
| KFP launcher init | 100m CPU / no memory request | 500m / 256Mi | KFP `launcherResources`; upstream records ~59Mi peak RSS while copying a ~123Mi binary. |
| Argo init executor | none | none | Injected from controller `executor` config; local ConfigMap supplies security context but no resources. |
| Argo wait executor | none | none | Same inherited empty resource configuration. Actual usage is `UNVERIFIED`. |
| Control-plane dependency init | 10m / 16Mi each | 100m / 64Mi each | Five Deployments; two API init containers are sequential. App resources dominate effective scheduling. |

The KFP API supplies immutable driver and launcher identities through `V2_DRIVER_IMAGE` and `V2_LAUNCHER_IMAGE`. Argo creates init/wait containers with `Config.GetExecutor().Resources`; because no resource field is configured, Kubernetes treats their requests and limits as zero/unbounded. This is configuration fact, not a claim of zero runtime consumption.

No new resource patch is justified offline. Adding executor or ephemeral limits without measured peak/working-set evidence could cause task eviction or artifact corruption.

### Concurrency and effective pod envelopes

The compiled graph contains three independent importers, followed by six dependency-ordered user components. The source compiler also creates driver phases before component execution. Expected configured maxima are:

- importer phase: three concurrent importer pods = **300m/192Mi requests; 1.5 CPU/1,536Mi limits**;
- component driver phase: one active driver = **100m/64Mi; 500m/512Mi**;
- component execution phase: one main task plus unrequested Argo wait container; launcher runs as an init container. Kubernetes effective resources remain **250m/512Mi requests; 1 CPU/2Gi limits**, because the main container exceeds launcher-init in each dimension;
- conservative per-resource workflow envelope: **300m CPU / 512Mi requested; 1.5 CPU / 2Gi limited**.

The CPU and memory maxima occur in different phases. Retry limit 2 is configured for `OnError`, but retries are sequential after a failed attempt; no retry-parallelism budget is claimed. Exact generated Workflow pod count and transient terminating/replacement overlap remain `UNVERIFIED` until API-server compilation and runtime observation.

### Ephemeral and temporary storage

Each component execution template defines seven unbounded KFP `emptyDir` volumes: launcher binary, GCS scratch, S3 scratch, MinIO scratch, `.local`, `.cache` and `.config`. Argo adds unbounded `/var/run/argo` and `/tmp` `emptyDir` volumes, for **nine unbounded volumes per execution pod**. There are no `sizeLimit` values or ephemeral-storage requests/limits. Driver/importer pods also inherit Argo's two unbounded volumes. Task outputs and artifact staging sizes depend on runtime inputs.

Historical synthetic artifacts show functional behavior but do not establish a safe upper bound. Workflow ephemeral storage therefore remains `UNVERIFIED` and is the principal offline resource-accounting gap.

## C. Recalculated capacity

### Control plane and replacement

The complete recursive render confirms M1-KFP3's control-plane totals:

| Envelope | CPU requests | Memory requests | CPU limits | Memory limits |
|---|---:|---:|---:|---:|
| Steady control plane | 884m | 3,164Mi | 6.5 CPU | 8,192Mi |
| Maximum configured simultaneous replacement surge | +720m | +2,396Mi | +4.5 CPU | +6,400Mi |
| Steady plus surge | 1,604m | 5,560Mi | 11 CPU | 14,592Mi |

The surge assumes one extra replica for every default one-replica RollingUpdate Deployment. Recreate MySQL and SeaweedFS do not surge.

### Workflow plus reserves

The kind configuration reserves 500m CPU/1,024Mi across system and Kubernetes reserves. Using the conservative configured workflow envelope:

| Scenario | CPU requests | Memory requests | CPU limits | Memory limits |
|---|---:|---:|---:|---:|
| Steady + one workflow + reserves | 1,684m | 4,700Mi | 8.5 CPU | 11,264Mi |
| Full replacement surge + one workflow + reserves | 2,404m | 7,096Mi | 13 CPU | 17,664Mi |

This corrects M1-KFP3 by adding the explicit three-importer CPU maximum: +50m requested and +500m limited. Memory totals are unchanged because the main training task remains the workflow memory maximum. Argo executor consumption is absent from these configured totals and remains unverified.

### Host headroom and storage

Fresh read-only host data: 12 logical CPUs, 15,705Mi total RAM, 11,257Mi available RAM, 141.42Gi free on `/`, and 7.48Gi free on `/tmp`.

- Against raw host capacity, the surge/workflow/reserve request envelope leaves about **9.60 CPU and 8,609Mi RAM** before container-runtime, kind-node and unrequested executor consumption.
- Against currently available RAM, it leaves about **4,161Mi** after known requests/reserves.
- The 12Gi available-memory gate is **FAIL**, short by about **1,031Mi**.
- Steady configured limits fit narrowly; surge limits exceed host CPU and RAM. Limits are ceilings, not scheduler reservations, but simultaneous pressure is unsafe until tested.
- PVC requirements remain two 20Gi ReadWriteOnce claims = **40Gi**. Nominal subtraction from root free space leaves about **101.42Gi**, without claiming filesystem/image overhead.
- Bounded control-plane `emptyDir` capacity remains **400Mi**. Workflow ephemeral storage is unbounded and `UNVERIFIED`.

## D. Validation

| Validation | Result |
|---|---|
| Complete recursive source render | **PASS**; actually executed from local KFP+Argo trees |
| Repeat render | **PASS**; byte-identical SHA-256 `060e410…f7a0` |
| M1-KFP3 manifest/semantic comparison | **PASS**; byte-identical |
| Manifest/image-ledger consistency | **PASS**; no unmatched rendered digest |
| Local S3 / cloud GCS role selection | **PASS** |
| Focused pipeline/resource/ledger tests | **PASS**; 59 passed, 3 warnings |
| Source/compiled pipeline synchronization | **PASS**; byte-identical SHA-256 `966393bc…268b4` |
| Ruff (`src scripts jobs dags pipelines`) | **PASS** |
| Git whitespace | **PASS** |
| Fresh full regression | **NOT REQUIRED**; M1-KFP4 changed no application or deployment source. M1-KFP3's 709-pass run remains prior evidence, not relabeled fresh. |

## E. Remaining runtime blockers

The following cannot be closed offline and explicitly require separately authorized isolated runtime access:

- actual Argo init/wait executor CPU, memory and ephemeral-storage peaks;
- generated Workflow pod topology, transient termination/retry overlap and task concurrency confirmation;
- training scratch/artifact/log sizes and safe ephemeral-storage requests/limits;
- combined controller, MySQL, MLMD, MLflow and SeaweedFS startup/steady peaks;
- real KFP run ID, task success/failure propagation, metadata lineage and restart behavior;
- host suitability after the 12Gi available-memory gate passes without disturbing retained resources;
- exact MLMD image availability, still blocked by the missing compressed layer in the inspected content store.

Separate non-runtime evidence gaps remain: the fresh Argo archive does not reproduce the retained archive checksum, and fresh commit-signature verification lacks the public key. Neither blocks semantic rendering from the exact Git commit, but both remain visible provenance limitations.

**M1-KFP4 result: `PARTIAL`; offline recursive rendering is closed, workflow accounting is materially improved, and runtime remains NO-GO / `UNVERIFIED`. `DEFER_KFP` stays in force. Stop here; do not initiate M1-KFP5 or another milestone.**
