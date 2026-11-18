# C5.8 final M10.3 runner qualification

**Qualification date:** 2026-11-17  
**Decision:** **PASS — local whole-image and offline-runtime qualification**

This PASS does not authorize publication, registry use, GitHub registration,
Kubernetes mutation or deployment. M10.3's local prerequisite is complete;
deployment remains NO-GO pending registry signing/attestation, immutable digest
review and explicit owner authorization. SEC-022 is unchanged.

## Inputs and controlled integration

The build consumed only the nine objects in
`deploy/gke/runners/deploy-inputs.SHA256SUMS`; the manifest SHA-256 is
`148e2f85e0062e63438841aea15cddf2099cd926904f310ca911974b7157c6e2`.
Every object passed `sha256sum --check --strict` inside the network-disabled
build.

| Component | Version / identity | SHA-256 |
|---|---|---|
| Actions Runner source candidate | 2.338.0, commit `a9dcf1bf7a78751648ff630fd4d0152471293487` | package `6d552c6b6acf854247f0b4c439586dd53196f54b94ba8320c76696d6a18d2e46` |
| kubectl | `v1.35.10-cogniflow.1` | `130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef` |
| Cosign | `v3.1.4-cogniflow.1` | `67a3ba89c77e654c3b3fe9507817ef9c3a3b802c7363781158f2ecf62bf5d901` |
| Helm | 4.3.2 | `876242ea89b1fc07692e179d9abdc47028979fb64b20d85448e85193c8b04931` |
| Trivy | 0.76.2 | `6a972c69606c7b3ea4c6bdcc6fc9332ea9ad38381624310c1e85cc77345909f3` |
| Google Cloud CLI | 594.0.0 | archive `8cf5b2d7987e7aac008264fecda7c083423227ecfb26878707bd20c6219d7dab` |
| Ubuntu `apt` | 2.8.4ubuntu0.1 | `ad2ea7f107f250ba88b0bfdba31812a341e3247589647aa2b03b9dc4e8abf8ed` |
| Ubuntu `libapt-pkg6.0t64` | 2.8.4ubuntu0.1 | `a50f3e68a793f90b05f44a4b5f2f59f3ec7687e39b5d8bbd1da44c84671fa3d6` |
| Ubuntu `libbrotli1` | 1.1.0-2ubuntu0.1 | `70b188a86d81f30d7510aab30e25d638ed5037dded6691af1533952b71ac61de` |

The inherited upstream Actions Runner base remains digest-pinned only as the
supported Ubuntu/runtime substrate. Its `/home/runner` payload is replaced by
the qualified source-candidate archive before the final layer is accepted.
The final image is not described as an official GitHub Actions Runner release.

## Resource preflight

- Available RAM: 4,491,636,736 bytes; memory PSI `avg10=0.00`
- Swap: 16,468,930,560 bytes total; 10,053,562,368 bytes used
- Persistent filesystem: 133,726,035,968 bytes available before the build
- `/tmp`: 228,024,320 bytes available, so Trivy and host scratch were explicitly
  redirected to persistent workspace storage
- Docker 29.9.1 with overlayfs: healthy
- Both `cogniflow-local` and `cogniflow-module1-qualification` control planes
  remained running and untouched

No Docker data was pruned and no existing container, image, volume, network or
cluster was stopped or changed.

## Exact final image and reproducibility

- Local OCI image/index ID:
  `sha256:fea8be5e98ba4defff5f8d23059c9d31103f7014b4e33b42c1aa1dcb0498d44a`
- Runtime manifest:
  `sha256:3aab5b8fe68d83df3608c6cb1f7b3c1b02798643c068345344a56b8816b2b182`
- Image config:
  `sha256:bf29264e5ddfd24271281885bac06ee55657150733d3228ceb7429a24ebd8edc`
- BuildKit attestation manifest:
  `sha256:af00971d3219f44aa0a9a12f9f65cfe4a0dbcff30d874243d3c17e69169b7774`
- Size: 4,937,850,322 bytes; linux/amd64; runtime user `1001:1001`

A second build reproduced the exact runtime manifest and config. Its outer OCI
index and attestation descriptor differ because it has a separately named
provenance subject; runtime bytes are identical.

## Whole-image security and attestations

Trivy 0.76.2 scanned the exact final image with the current retained schema-2
vulnerability and Java databases. It detected supported Ubuntu 24.04, 225 OS
packages and 12 language-specific targets, and completed OS, .NET, Go and
Python analysis without a scanner error or suppression.

- Result: **0 HIGH / 0 CRITICAL**, mandatory exit code 0
- Trivy JSON SHA-256:
  `81924597d2acb40c89350e2e13d3b0481c1c26b95ef6475e08e607a7374217a2`
- Independent SPDX 2.3 SBOM: 1,463 packages, SHA-256
  `1f1c578b6c191a87bb8e7355930e732db996e62c6069f2679b44605bf8aa9736`
- BuildKit provenance metadata SHA-256:
  `394ce1aa17e5f6a7c0faab57bc450e453b35718b3eae307f067bd07302a64bac`

BuildKit emitted both maximum-mode provenance and its SBOM attestation. Raw
reports and build metadata remain under ignored local `build/` evidence and
contain no credentials.

## Offline runtime results

Only after the scan passed, a network-disabled, unregistered container was
started with a read-only root and bounded writable runner-home/tmp mounts.

- Runner version and commit: 2.338.0 / `a9dcf1bf...` — PASS
- Embedded kubectl and Cosign checksums and versions — PASS
- Helm lint and GKE render — PASS
- Google Cloud CLI and Trivy availability — PASS
- Node 24.22.3 and real `hashFiles` fixture digest — PASS
- Controlled local Cosign key generation, blob signing and verification — PASS
- Docker and sudo absent — PASS
- No kubeconfig or network: kubectl access failed closed — PASS
- Qualified kubectl read-only `/version` against the existing v1.34.11
  qualification cluster — PASS from the host with the owner-only inspect
  kubeconfig; its permissions were not weakened or copied into the container

The controlled test signature deliberately used an empty-service signing
configuration and local test key. Transparency-log verification is therefore
not claimed; registry signing remains a separate publication gate.

The runtime check also found and fixed an existing non-root staging defect:
`cp -a` tried to preserve metadata on the mounted volume root and failed. Both
runner pods now use `cp -r`, which retains executable file modes without trying
to preserve root ownership/timestamps. No Kubernetes resource was applied.

All test-owned containers exited and were removed. Both kind clusters remained
running.

## Repository validation

- Focused M10/GKE/schema/security: **38 passed / 5 skipped**
- Full Python regression: **631 passed / 5 skipped / 5 warnings**
- Coverage: **87.20%**, above the required 81%
- Ruff: PASS
- Scoped MyPy: PASS for the two M10/schema validators; untyped third-party
  PyYAML/jsonschema imports were excluded, with no source error suppressed
- Shell syntax, YAML load and Git whitespace checks: PASS
- Two-build runtime-manifest reproducibility: PASS

The initial sandboxed full-suite attempt could not bind its loopback tracing
server and was interrupted after the next test hung. The unchanged suite passed
completely when rerun with loopback binding available.

## Remaining gates

The local M10.3 qualification is **PASS**. Before C5 Kubernetes acceptance can
execute, an owner must review this record, publish the exact runtime manifest
to the approved registry, produce and verify registry signatures/attestations
and SBOM association, substitute an immutable `repository@sha256` reference,
and separately authorize credentials and cluster mutation. No runner was
registered and no Kubernetes or cloud object changed during C5.8.
