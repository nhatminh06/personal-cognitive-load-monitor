# M1-KFP2 — KFP release evidence and resource ledger reconciliation (2026-11-21)

**Decision: BLOCKED.** The exact selected headless configuration cannot be fully reconstructed from verified local source. The active MySQL ID has no matching retained assessment, the MLflow ledger differs from the active patch, and the KFP 2.18.1 remote base and C22 73-object render are unavailable locally. This is an offline reconciliation result; `DEFER_KFP` remains in force. No Kubernetes, Docker, MLMD, cloud or registry operation was performed.

## A. Repository baseline

- Branch `main`; HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. Pre-existing modifications and all evidence were preserved. The only new tracked-path file for this milestone is this report.
- Read `AGENTS.md`, [M1-KFP1](module1-m1-kfp1-security-resource-feasibility-2026-11-21.md), C14–C23 reports and assessment JSONs, [M1-KS1](../security-audit/module1-m1-ks1-exact-digest-security-2026-11-21.md), `infra/kfp-local`, the release ledger, C11 preflight/acceptance contract and the six-component compiled pipeline.
- Authoritative **active source** is `infra/kfp-local/kustomization.yaml`, whose first resource is the exact upstream KFP Git commit `7dd28116ad652bfb7b6c282e7920be84e6a7634a`, plus local patches and `infra/kfp-local/mlflow.yaml`. `deploy/releases/kfp-local-images.json` is a local-ID ledger, not an OCI registry release manifest. C11 preflight requires a separate complete, signed, remotely scanned image ledger and an approved controller matrix; its current plan has neither.
- Retained C22 assessment reports a 73-object, 16-image-use render SHA-256 `6dc13b9fedfb4f8b528f87a5f6be33175bf1a9f29c11c1bf95d279b100f13322`. The render bytes and exact KFP upstream source checkout are absent from available verified local inputs. A different Kubeflow manifests checkout at commit `f121d4...` is **not** the selected KFP source and was not substituted.
- Task-owned ignored evidence: `build/m1-kfp2-2026-11-21/` contains the reconciliation script, role and partial resource JSON, source-file SHA-256 list, and a byte-identical compiled-pipeline check. All listed source checksums verified locally. Historical raw C14–C23 Trivy/SBOM artifacts named only by assessment hashes were not found; their hashes cannot be independently checked without the original files. Assessment JSON bytes were checksummed, which is narrower than validating raw scan bytes.

## B. All 15 image-role identities

The `active` column is an exact reference found in local overlay patches, an embedded controller argument/variable, or the compiled pipeline. `UNVERIFIED_BASE` means the role appears in historical C19/C22 evidence and ledger but its current active reference is inherited from the unavailable upstream base. All `sha256:` ledger values are **local image/index IDs**, even when used in local `name@sha256:` syntax; no published OCI manifest digest, remote signature or digest-bound attestation has been verified. Classifications are primary offline reconciliation labels; every role also has `PUBLICATION_PENDING` as a release-wide secondary gate.

| Role | Active selected reference or source | Ledger local ID | Matching assessment ID / result | Class |
|---|---|---|---|---|
| kfp-api | `cogniflow-kfp-api@sha256:d70accf415ef407fd23fd7a790cfd8f9ec9877324018434264fdb66d378859ad` | `sha256:d70accf415ef407fd23fd7a790cfd8f9ec9877324018434264fdb66d378859ad` | `sha256:d70accf415ef407fd23fd7a790cfd8f9ec9877324018434264fdb66d378859ad`; 0 H / 0 C (c16-evidence) | **MATCHED_LOCAL** |
| persistence-agent | `cogniflow-kfp-persistence-agent@sha256:707c3af5abdb6c57902036916fd0d74d6bb014889a30c19e16574a71c92a68dc` | `sha256:707c3af5abdb6c57902036916fd0d74d6bb014889a30c19e16574a71c92a68dc` | `sha256:707c3af5abdb6c57902036916fd0d74d6bb014889a30c19e16574a71c92a68dc`; 0 H / 0 C (c16-evidence) | **MATCHED_LOCAL** |
| scheduled-workflow | `cogniflow-kfp-scheduled-workflow@sha256:9fa52c2f7e8a6eb62df0e38afec42be1d44cd15ffd85cd3942b2910455d491f3` | `sha256:9fa52c2f7e8a6eb62df0e38afec42be1d44cd15ffd85cd3942b2910455d491f3` | `sha256:9fa52c2f7e8a6eb62df0e38afec42be1d44cd15ffd85cd3942b2910455d491f3`; 0 H / 0 C (c16-evidence) | **MATCHED_LOCAL** |
| workflow-controller | `cogniflow-argo-workflow-controller@sha256:c115303d506de611f4d230c1a3f234eb7b1feae153c755a79dad56ebb91b44fd` | `sha256:c115303d506de611f4d230c1a3f234eb7b1feae153c755a79dad56ebb91b44fd` | `sha256:c115303d506de611f4d230c1a3f234eb7b1feae153c755a79dad56ebb91b44fd`; 0 H / 0 C (c16-evidence) | **MATCHED_LOCAL** |
| workflow-executor | `cogniflow-argoexec@sha256:f597b17060742da11004bd5badc1a401cb65125035fcdb1f6550c802a4515802` | `sha256:f597b17060742da11004bd5badc1a401cb65125035fcdb1f6550c802a4515802` | `sha256:f597b17060742da11004bd5badc1a401cb65125035fcdb1f6550c802a4515802`; 0 H / 0 C (c16-evidence) | **MATCHED_LOCAL** |
| kfp-driver | `cogniflow-kfp-driver@sha256:175b9bbf02a4fde6211a6716dc499524236729b30dd75e6cd2362fc25480f963` | `sha256:175b9bbf02a4fde6211a6716dc499524236729b30dd75e6cd2362fc25480f963` | `sha256:175b9bbf02a4fde6211a6716dc499524236729b30dd75e6cd2362fc25480f963`; 0 H / 0 C (c16-evidence) | **MATCHED_LOCAL** |
| kfp-launcher | `cogniflow-kfp-launcher@sha256:8e2f3860b0853bd841c8fc86113f5fe3d9964f7e87ebf693cd064abfd57ad9c5` | `sha256:8e2f3860b0853bd841c8fc86113f5fe3d9964f7e87ebf693cd064abfd57ad9c5` | `sha256:8e2f3860b0853bd841c8fc86113f5fe3d9964f7e87ebf693cd064abfd57ad9c5`; 0 H / 0 C (c16-evidence) | **MATCHED_LOCAL** |
| metadata-envoy | `ghcr.io/kubeflow/kfp-metadata-envoy@sha256:bf7ad93d1c0621f0081e1c2f5be1e96b6955b2615115564837f88b3e95c33126` | `sha256:bf7ad93d1c0621f0081e1c2f5be1e96b6955b2615115564837f88b3e95c33126` | `sha256:bf7ad93d1c0621f0081e1c2f5be1e96b6955b2615115564837f88b3e95c33126`; 0 H / 0 C (c19-evidence) | **MATCHED_LOCAL** |
| init-helper | `UNVERIFIED_BASE; C19/C22 historical only` | `sha256:469c9ea410b9215eaee7976ba6c0639039b444be8e5d638f7abbada189971eb2` | `sha256:469c9ea410b9215eaee7976ba6c0639039b444be8e5d638f7abbada189971eb2`; 0 H / 0 C (c19-evidence) | **PUBLICATION_PENDING** |
| mysql | `cogniflow/mysql@sha256:febda51c2aa5e451cb2d4161f1c82f731dc5e36cbf06be80eea4ed17e9dcb5e6` | `sha256:febda51c2aa5e451cb2d4161f1c82f731dc5e36cbf06be80eea4ed17e9dcb5e6` | `sha256:367c695a6870d1fed993457575846f13071ea3c8cee88d54a311251ff4dbf0f3`; 0 H / 0 C (c18-evidence) | **SCAN_MISSING** |
| mlflow-gcs | `cogniflow-mlflow@sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5` | `sha256:a9741a4d3248444027c0f605114024e2294e25504cde7b5def31c18694f445f5` | `sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5`; 0 H / 0 C (c20-evidence) | **IDENTITY_MISMATCH** |
| seaweedfs | `UNVERIFIED_BASE; C19/C22 historical only` | `sha256:4b42c212543a0acd4c0e675215ecdcaf62a186ef98def76c7e12701871222d15` | `sha256:4b42c212543a0acd4c0e675215ecdcaf62a186ef98def76c7e12701871222d15`; 0 H / 0 C (c19-evidence) | **PUBLICATION_PENDING** |
| mlmd | `cogniflow-mlmd@sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876` | `sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876` | `sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876`; 0 H / 0 C (c21-evidence) | **MATCHED_LOCAL** |
| metadata-writer | `cogniflow-metadata-writer@sha256:c2a8d2322156040087818323c1e5d1e685dbb63142f52bad263512fb00fa2ae1` | `sha256:c2a8d2322156040087818323c1e5d1e685dbb63142f52bad263512fb00fa2ae1` | `sha256:c2a8d2322156040087818323c1e5d1e685dbb63142f52bad263512fb00fa2ae1`; 0 H / 0 C (c22-evidence) | **MATCHED_LOCAL** |
| training-component | `cogniflow-kfp@sha256:e296269ccaa235661a1102c49bc98754f5a3d07e80c8c59e5e78d83a8cc2d1f9` | `sha256:e296269ccaa235661a1102c49bc98754f5a3d07e80c8c59e5e78d83a8cc2d1f9` | `sha256:e296269ccaa235661a1102c49bc98754f5a3d07e80c8c59e5e78d83a8cc2d1f9`; 0 H / 0 C (c23-evidence) | **MATCHED_LOCAL** |

Eleven roles match exact local patch/compiled identity, ledger ID and recorded 0/0 local scan assessment. `init-helper` and `seaweedfs` match their historical C19 local assessments and ledger but cannot be reverified against the absent current base; they are classified `PUBLICATION_PENDING` with an explicit active-reference gap. MySQL is `SCAN_MISSING` for its active ID. MLflow is `IDENTITY_MISMATCH`. No role is claimed published or signed. The complete machine-readable comparison is `image-reconciliation.json`.

## C. MySQL evidence disposition

Active `infra/kfp-local/mysql.yaml` and the current ledger both select local ID `sha256:febda51c2aa5e451cb2d4161f1c82f731dc5e36cbf06be80eea4ed17e9dcb5e6`. The latest attributable C18 assessment instead scanned and functionally tested `sha256:367c695a6870d1fed993457575846f13071ea3c8cee88d54a311251ff4dbf0f3` at 0/0, with raw scan SHA-256 `b056d612e5a93a08961e555e1022d117abbc3ee6d4a1aa935c442fa011b324dc` and SBOM SHA-256 `f48d812bf3c9f96d081be2ebb86356b9f57096655892cf476e51938d33dfee5b`. C21’s runtime used that C18 ID. The old C16 PostgreSQL and failed C16.3 MySQL candidate are superseded for the selected path, but neither qualifies the new ID. No matching `febda...` scan/SBOM provenance was located. **Security status for active MySQL: UNVERIFIED; do not relabel the C18 scan or alter the ledger to force a match.**

## D. MLflow identity mismatch disposition

The active `infra/kfp-local/mlflow.yaml` selects `cogniflow-mlflow@sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5`. C20 assessed precisely that local ID at 0/0, with scan SHA-256 `22013078449571e9a4eeaf81fd027b26319155d81a15ad7a7b458d5c29677335` and SBOM SHA-256 `67976750e7a512182d2d4106f2992115044804a34b5cd466a6b1b0ac8ae28c49`. The release ledger instead selects `mlflow-gcs` ID `sha256:a9741a4d3248444027c0f605114024e2294e25504cde7b5def31c18694f445f5`; `docs/evidence.md` calls it a locally 0/0 qualified GCS image. That does not prove behavioral or byte equivalence to the active S3-targeted overlay image. **Keep the mismatch unresolved** until the intended runtime (S3 versus GCS) is selected and its exact render/scan/provenance are reconciled. No production manifest or ledger was edited.

## E. Resource and PVC ledger

The 13 local overlay YAML files parse as 14 YAML documents. Nine patched container definitions are visible; six provide explicit resources, while the API server, persistence agent and workflow controller patches omit resource fields and inherit any values from the unavailable base. No local patch defines an init container or PVC. That absence does **not** mean the rendered stack has none: C22 reports 16 image uses and the upstream base is required. `partial-resource-ledger.json` retains every visible patched container, source file, image, replica field and resource value.

| Visible patched container | Request CPU / RAM | Limit CPU / RAM | Replica certainty |
|---|---:|---:|---|
| MySQL | 100m / 512Mi | 1 / 1Gi | base unknown |
| MLMD | 25m / 64Mi | 500m / 256Mi | base unknown |
| Metadata Envoy | 50m / 64Mi | 250m / 256Mi | base unknown |
| Metadata writer | 25m / 128Mi | 500m / 512Mi | base unknown |
| Scheduled workflow | 50m / 128Mi | 250m / 256Mi | base unknown |
| MLflow | 100m / 512Mi | 1 / 2Gi | explicit 1 |
| API / persistence agent / workflow controller | inherited or missing | inherited or missing | base unknown |
| One of six sequential training components | 250m / 512Mi | 1 / 2Gi | max one by pipeline graph |

Six explicitly bounded patched services total **350m CPU / 1,408Mi RAM requests** and **3.5 CPU / 4,352Mi limits** for one replica of each. With one training task, the known lower bound is **600m / 1,920Mi requests** and **4.5 CPU / 6,400Mi limits**. These are arithmetic checks, not a complete scheduler total or observed peak. C11 kind configuration reserves 250m/512Mi system plus 250m/512Mi kubelet = **500m CPU / 1Gi RAM**, and has one control-plane node, so no single-node-loss tolerance. The full render is needed to count other workloads, actual replicas, init/sidecar resources, PVC sizes/storage classes, ephemeral storage, pod replacement surge and max concurrent Argo/KFP run pods. Do not assume missing requests are zero or limits represent usage. C20/C21/C22 historical memory measurements came from separate local tests, not the combined stack.

Host snapshot: `MemAvailable` **9,746,374,656 bytes (9.08 GiB)**, below C11/C22’s **12 GiB (12,884,901,888 bytes)** requirement by **3,138,527,232 bytes (2.92 GiB)**. Root free disk **151,417,769,984 bytes (141.02 GiB)** exceeds the 60 GiB threshold; exact PVC/image/cache needs remain unknown. Swap is excluded from available RAM. **Resource ledger: INCOMPLETE; current host: NO-GO.**

## F. MLMD defect assessment

Affected selected local image: `sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876`; C21 records preserved upstream MLMD 1.14 server binary SHA-256 `d170da72e14dfc4726f7f9cfbe48d57cfa4c0dedbe42a8224880be5d879aa584`. C21/C22 report that invalid MySQL credentials trigger `mysql_real_connect` failure followed by process exit 139 / SIGSEGV, with OOM false. Fresh test database table count remained zero, authentication was rejected, no unauthorized writes or test-password log leak were observed. This is an availability/correctness failure on credential error, not evidence of successful unauthorized access. Root cause inside the native binary is not established; no matching crash dump, stack trace, upstream fix commit or verified corrected release is recorded.

The [upstream MLMD MySQL 8 authentication issue](https://github.com/google/ml-metadata/issues/178) documents the `mysql_native_password` compatibility constraint, but does not establish a fix for this SIGSEGV. A supported upstream MLMD release with a verified error-path fix is a possible remedy only after checking KFP 2.18.1/schema compatibility and passing the same negative test under a separate milestone. Narrow follow-up: obtain a symbolic stack trace/source-level failure location for the exact preserved binary and an upstream-maintainer disposition; do not patch or run it here. Restart policy may contain outage duration but cannot make the crash a passing negative-auth test.

## G. Verification results

- `sha256sum -c build/m1-kfp2-2026-11-21/source-checksums.sha256`: **PASS** for the release ledger, C11 plan/matrix, overlay root, compiled pipeline, M1-KFP1 report and all tracked C14–C23 assessment JSONs. This verifies the present document bytes only; historical raw scan/SBOM hashes remain **UNVERIFIED** because those files are absent.
- Reconciliation script: **15 roles**, 11 `MATCHED_LOCAL`, 2 `PUBLICATION_PENDING` with active-base gap, 1 `SCAN_MISSING`, 1 `IDENTITY_MISMATCH`. Resource validator: nine patch containers, six explicit budgets, known sums 350m/1,408Mi requests and 3.5 CPU/4,352Mi limits; three patch budgets inherited/unknown. The exact 73-object resource ledger remains **INCOMPLETE**.
- Focused ledger, C11, controller, MySQL, MLflow, MLMD, pipeline and task tests: **47 passed**, one SQLAlchemy deprecation warning. Fresh pipeline compile SHA-256 `966393bcacb604e09875f4dcd80c8430ee36fa2c9a253606d53567508f3268b4` matched tracked `pipelines/compiled/cogniflow-training.yaml` byte for byte.
- Ruff on the task-owned reconciliation script and `.venv/bin/ruff check src scripts jobs dags pipelines`: **PASS**. Local overlay YAML parse: **PASS**. `git diff --check`: **PASS**. No Kustomize fetch/render or Kubernetes schema assertion was attempted from the unavailable exact base; the C22 73/73 check remains historical.

## H. Remaining security and publication gaps

Active MySQL scan/SBOM and source provenance are missing. MLflow identity selection is unresolved. Init helper and SeaweedFS active references cannot be confirmed without the exact base render. All 15 local IDs lack verified published OCI manifest identities, Cosign signatures, remote SPDX/SLSA attestations and final remote scans. C11 controller matrix remains blocked, and M1-KS1 independently blocked the KServe ecosystem. No model approval, cloud or production gate is satisfied.

## I. Recommended next milestone

Recover or vendor the **exact KFP source commit and C22 render bytes** with verifiable SHA-256, then calculate the complete 73-object workload/PVC/ephemeral-storage and replacement-surge ledger. Separately recover an attributable scan/SBOM/build record for active MySQL `febda...`, or select an already qualified image through a reviewed manifest change in a later authorized task. Decide which MLflow implementation the headless S3 contract requires and make ledger, overlay and scan identity agree. Investigate MLMD’s negative-auth crash at the exact binary/source boundary. These are concrete closure tasks; do not start Kubernetes, publish images or request runtime approval as part of this milestone.

## J. Final decision

**BLOCKED — exact source/render and evidence gaps prevent reliable full reconciliation.** M1-KFP2 resolved the nature of the MySQL and MLflow inconsistencies and produced a verifiable partial ledger, but did not create the missing scan or full capacity proof. `DEFER_KFP` remains in force. KServe and Spark remain BLOCKED; cloud and production remain NOT QUALIFIED.
