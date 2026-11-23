# M1-KFP3 — independent offline resource and ledger remediation (2026-11-21)

**Decision: OFFLINE REMEDIATION COMPLETE; RUNTIME SUITABILITY `UNVERIFIED`.** Four control-plane workloads now have explicit CPU and memory requests and limits, and the release ledger now represents local S3 and cloud GCS MLflow as distinct roles without transferring evidence between digests. Static and unit validation passed. No Docker, containerd, Kubernetes, MLMD diagnostic, cloud, registry, signing, model approval, commit, or push operation occurred. `DEFER_KFP` remains unchanged.

## Scope and changed files

Resource-only changes:

- `infra/kfp-local/kfp-api.yaml`: preserved upstream 250m/500Mi requests; added 1 CPU/1Gi limits.
- `infra/kfp-local/persistence-agent.yaml`: preserved upstream 120m/500Mi requests; added 500m/1Gi limits.
- `infra/kfp-local/workflow-controller.yaml`: preserved upstream 100m/500Mi requests; added 500m/1Gi limits.
- `infra/kfp-local/seaweedfs.yaml`: new strategic-merge patch preserving upstream 64m/256Mi requests and adding 1 CPU/768Mi limits.
- `infra/kfp-local/kustomization.yaml`: includes the SeaweedFS resource patch.

Ledger/test changes:

- `deploy/releases/kfp-local-images.json`: added an explicit `mlflow-s3` role and its digest-specific C20 metadata; retained `mlflow-gcs` and all other identities unchanged.
- `src/tests/test_kfp_release_inventory.py`: checks both distinct MLflow roles, exact overlay-to-S3 identity, and all four resource budgets.

This report is the only other tracked-path addition. Unrelated modified/untracked files and unpublished commits were preserved.

## A. Resource-budget basis

The recovered KFP source is commit `7dd28116ad652bfb7b6c282e7920be84e6a7634a`. Its exact retained 73-object render showed that the four target workloads inherited upstream requests but had no CPU or memory limits. The selected limits are proposed local safety ceilings, not measured combined-runtime requirements.

| Workload | Requests | New limits | Evidence and limitation |
|---|---:|---:|---|
| KFP API server | 250m / 500Mi | 1 CPU / 1Gi | Requests are upstream KFP defaults. Historical isolated API use was 20.84 MiB, but that did not exercise a complete KFP run, so the upstream memory request was not reduced. |
| Persistence agent | 120m / 500Mi | 500m / 1Gi | Requests are upstream defaults. No attributable runtime peak exists; the 2-worker configuration and one-workflow target support a bounded local ceiling, subject to runtime validation. |
| SeaweedFS | 64m / 256Mi | 1 CPU / 768Mi | Requests are upstream defaults. Historical isolated peaks were 150.5–175.1 MiB under authenticated persistence/restart tests; the 768Mi ceiling matches the prior bounded C19 runtime. It is not a production-load measurement. |
| Argo workflow controller | 100m / 500Mi | 500m / 1Gi | Requests are upstream Argo/KFP values. No attributable controller peak exists; the ceiling is a local one-workflow proposal requiring live confirmation. |

No ephemeral-storage request/limit was added because retained evidence does not measure API, controller, launcher, executor, or training writable-layer usage. Adding arbitrary values would create an eviction risk disguised as certainty.

## B. Complete rendered control-plane calculation

The offline patched render contains 73 objects, ten single-replica Deployments, two PVCs, 16 container/init image uses and 11 unique image references.

| Envelope | CPU requests | Memory requests | CPU limits | Memory limits |
|---|---:|---:|---:|---:|
| Steady control plane | 884m | 3,164Mi | 6.5 CPU | 8,192Mi |
| Maximum simultaneous replacement surge | +720m | +2,396Mi | +4.5 CPU | +6,400Mi |
| Steady plus surge | 1,604m | 5,560Mi | 11 CPU | 14,592Mi |

The surge calculation assumes every default `RollingUpdate` Deployment replaces simultaneously and gains one extra replica (`maxSurge: 25%` rounded up for one replica). MySQL and SeaweedFS use `Recreate`, so they add no replacement replica. This is conservative for coordinated upgrades, not a claim that all workloads normally roll together.

Five Deployments have init containers. Each init container requests 10m/16Mi and limits 100m/64Mi; the API has two that run sequentially. Kubernetes schedules a pod using the larger of the summed app-container resources or the largest init-container resources. In every affected pod the app-container value is larger, so init containers do not increase the effective request/limit totals above. Their transient usage remains unmeasured.

## C. One complete training workflow

The compiled graph has six user components in a dependency chain; only one user component is expected active at a time. Each main task declares 250m/512Mi requests and 1 CPU/2Gi limits. Therefore the known configured lower bounds are:

| Scenario | CPU requests | Memory requests | CPU limits | Memory limits |
|---|---:|---:|---:|---:|
| Steady control plane + one active task | 1,134m | 3,676Mi | 7.5 CPU | 10,240Mi |
| Replacement surge + one active task | 1,854m | 6,072Mi | 12 CPU | 16,640Mi |

KFP driver, launcher and Argo wait/executor overhead have no resource declarations in the recovered render or compiled pipeline. The launcher participates in task execution and Argo injects executor behavior, but their schedulable overhead cannot be represented as a verified nonzero quantity from these manifests. Consequently the table is a **lower bound**, not a complete measured runtime requirement. No arbitrary overhead budget was patched in. Runtime acceptance must measure those processes and then set resource declarations if they are separate containers in the generated Workflow.

## D. Kubernetes/host reserve and headroom

`infra/kfp-local/kind-config.yaml` reserves 250m/512Mi for the system and 250m/512Mi for Kubernetes: 500m CPU and 1,024Mi total. With that reserve:

| Scenario | Known requested CPU | Known requested memory |
|---|---:|---:|
| Steady + one task + reserve | 1,634m | 4,700Mi |
| Full replacement surge + one task + reserve | 2,354m | 7,096Mi |

Fresh host inspection found 12 logical CPUs, 15,705Mi total RAM, 11,617Mi available RAM, 141.48Gi free on `/`, and 7.61Gi free on `/tmp`. Against raw capacity, the surge/request scenario leaves about 9.65 CPU and 8,609Mi RAM before the unbounded driver/launcher/executor, container-runtime, kind-node and image-cache costs. Against currently available RAM it leaves about 4,521Mi after the known workload and configured reserve.

The established **12Gi available-memory gate still fails by about 671Mi**. Configured limits are not scheduler reservations: steady + task + reserve limits total 8 CPU/11,264Mi, while surge + task + reserve limits total 12.5 CPU/17,664Mi and exceed host capacity. This overcommit is another reason runtime suitability remains `UNVERIFIED`.

## E. Storage

- MySQL PVC: 20Gi ReadWriteOnce.
- SeaweedFS PVC: 20Gi ReadWriteOnce.
- Total declared PVC capacity: 40Gi. Subtracting nominal claims from current root free space leaves about 101.48Gi, above the historical 60Gi free-disk gate, but kind/container storage allocation and filesystem overhead were not exercised.
- Explicit bounded `emptyDir` capacity totals 400Mi: MLflow 256Mi, metadata writer 64Mi, and MySQL 80Mi.
- API/controller writable layers, dynamically generated workflow pods, driver/launcher/executor storage, training scratch space, logs, image layers and artifact staging have no complete ephemeral-storage requests/limits. Their requirement is `UNVERIFIED`.
- The exact MLMD OCI index/amd64 manifest/configuration inspection remains historical input to this milestone; its missing first compressed layer means runtime image availability remains `UNVERIFIED`.

## F. MLflow release-ledger reconciliation

The two identities are distinct deployment roles:

| Role | Local identity | Evidence boundary |
|---|---|---|
| `mlflow-s3` | `sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5` | Selected by `infra/kfp-local/mlflow.yaml`; C20 tested MySQL backend plus SeaweedFS S3 artifacts and recorded digest-specific 0 HIGH/0 CRITICAL scan/SBOM evidence. |
| `mlflow-gcs` | `sha256:a9741a4d3248444027c0f605114024e2294e25504cde7b5def31c18694f445f5` | Retained for the cloud/GCS role with its separate runtime manifest and local 0/0 ledger record; not selected by the local S3 overlay. |

The ledger now contains both roles rather than labeling the local S3 deployment as GCS. No security, runtime, manifest, SBOM or provenance evidence was copied between digests. Both `published_reference` values remain null; neither identity is promoted to a published OCI release.

Repository consumers are limited to the ledger regression test and documentation; the active overlay owns its exact image reference directly. The new regression binds that overlay reference to `images.mlflow-s3` and asserts it differs from `images.mlflow-gcs`.

## G. Offline validation

- Recursive local-source Kustomize attempt: **BLOCKED OFFLINE**. The recovered KFP tree still references Argo Workflows 4.1.6 through a GitHub Kustomize URL, and no local Argo source/cache is retained. The network-disabled attempt failed before output; nothing was fetched. This is not reported as a render pass.
- Offline patch render: **PASS** using the retained 73-object render previously generated from the exact recovered KFP source as an immutable base. Two `kubectl kustomize` client-only builds (Kustomize v5.7.1, no API operation) are byte-identical at SHA-256 `060e410a8240bd60acee65014baa6152d7e0793647a5ddc9e8c6cdbd172cf7a0`.
- Resource inventory/capacity assertions: **PASS** for the values in sections B–E.
- Focused KFP/MLflow/ledger/training tests: **44 passed**, 3 warnings.
- Full `make test`: **709 passed, 2 skipped**, 5 warnings, 87.00% coverage. The sandbox run could not bind a localhost tracing socket; the required rerun outside that socket restriction passed and performed no Docker/Kubernetes/cloud access.
- Source/compiled KFP pipeline synchronization: **PASS byte-identical**, SHA-256 `966393bcacb604e09875f4dcd80c8430ee36fa2c9a253606d53567508f3268b4`.
- Focused Ruff: **PASS**. `.venv/bin/ruff check src scripts jobs dags pipelines`: **PASS**. Final `git diff --check`: **PASS**.

Sanitized machine-readable results and the two identical renders are retained under ignored `build/m1-kfp3-2026-11-21/`.

## H. Remaining blockers and decision

- Runtime suitability, actual controller/task peaks, init startup consumption, launcher/executor/driver overhead, and ephemeral-storage use remain `UNVERIFIED` until an owner-authorized isolated workload test.
- The host fails the existing 12Gi available-memory gate despite passing the known scheduler-request calculation.
- The exact MLMD image is not runnable from the inspected content store because a required compressed layer was absent; further MLMD diagnostic preparation is deferred.
- Current MySQL exact-image evidence, remote publication/signatures/attestations, complete security gates, Kubernetes compatibility, real KFP run ID/failure behavior, reviewed Secrets and explicit runtime authorization remain unresolved.

**Milestone result: offline configuration gaps addressed; `DEFER_KFP` / NO-GO for runtime remains in force.** Stop here. Do not activate Docker/containerd, access either retained cluster, initiate a KFP run, or start another preparation milestone automatically.
