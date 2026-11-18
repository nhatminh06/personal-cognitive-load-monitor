# C5.5 qualified kubectl runner integration

**Qualification date:** 2026-11-17

**Decision: NO-GO.** The qualified kubectl is integrated correctly and remains
byte-identical inside the image, but the mandatory complete-image scan reports
5 HIGH and 0 CRITICAL findings outside kubectl. No suppression, exception,
cluster mutation, cloud operation, publication or runner execution occurred.

## Preflight and preserved identity

- Starting source commit:
  `15825b4f87fb54cb2c22d25a7f01fe172a0c7787`
- Starting runner image:
  `sha256:dfd51490064d4834bc00cfbddc35f7f151d0c274ccec10270eb45cf790d1cde2`
- Starting runner tag: `cogniflow-deploy-runner:m10-2-final`
- Base: Actions Runner 2.338.2 linux/amd64 at
  `sha256:0ce3288e48b012a83685998f683a2ae0cbd284fa722c090dda0af5443215cf30`
- Pre-build resources: 6.1 GiB available RAM, 140 GiB persistent disk and
  3.6 GiB `/tmp`; Docker 29.9.1 with overlayfs was healthy.
- All five preserved M10.2 inputs passed their old checksum manifest before a
  separate C5.5 context was assembled. No old binary or image was overwritten.

## Controlled integration and reconstruction

The only tool substitution is kubectl:

- Required version: `v1.35.10-cogniflow.1`
- Required SHA-256:
  `130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef`
- Kubernetes upstream commit:
  `ae6fece6fea92ecfcccd13af7d5f2ea8cb9b33fe`
- Compatibility boundary: Kubernetes client minor 1.35 against server 1.34

`build-qualified-kubectl.sh` downloads the authenticated Kubernetes v1.35.10
source archive and Go 1.27.4, verifies their pinned hashes and the Kubernetes
Sigstore identity, applies the fixed Go module closure, builds with two workers,
and refuses to install output unless the final binary hash matches. An
end-to-end invocation recreated the exact expected binary. The initial test
exposed read-only Go-cache cleanup; the script now makes only its random
test-owned cache writable before removing it and installs output only after the
checksum passes.

The runner build used an empty primary context, the five-file verified artifact
context, `--network=none`, `--pull=false`, linux/amd64, maximum BuildKit
provenance, and BuildKit SBOM generation. Build-time checks independently
validated every input hash and exact tool version.

## Exact image and tool ledger

- Image/index ID:
  `sha256:073432d2da9a1c4ceb18ca7d3654984fbed88635d207ab59407b65c01f70d8a7`
- Platform and user: linux/amd64, `1001:1001`
- Size: 4,080,849,128 bytes
- OCI manifest:
  `sha256:d3ac9b228cbe888db083cd0ca8dcc6ba966286d53a0c2d69bca02220f97fb1e4`
- Image config:
  `sha256:6d725187f032f590c685d9f8f95a353ff4cd2f1c6c49523509f41b5a47fe0504`
- BuildKit attestation manifest:
  `sha256:8a2b17c01813108a04550c386b5047b2b0b44bcf8fc93bc73a270d8bbf62f70e`

| Runtime component | Version / identity | Extracted or input SHA-256 |
|---|---|---|
| Actions Runner | 2.338.2 | base digest above |
| Cosign | 3.1.4 | `424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa` |
| Helm | 4.3.2 | `876242ea89b1fc07692e179d9abdc47028979fb64b20d85448e85193c8b04931` |
| kubectl | `v1.35.10-cogniflow.1` | `130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef` |
| Trivy | 0.76.2 | `6a972c69606c7b3ea4c6bdcc6fc9332ea9ad38381624310c1e85cc77345909f3` |
| Google Cloud CLI | 594.0.0 | archive `8cf5b2d7987e7aac008264fecda7c083423227ecfb26878707bd20c6219d7dab` |

The complete independent SPDX 2.3 SBOM contains 1,463 packages, including the
Ubuntu 24.04 OS packages, Actions Runner .NET payload, bundled Node runtimes,
Google Cloud CLI Python runtime and every detected Go binary. Trivy detected a
supported Ubuntu 24.04 OS, 225 OS packages and 12 language-specific targets and
completed OS, .NET, Go and Python analysis without a scanner error.

## Whole-image security result

Trivy 0.76.2 used database schema 2 updated 2026-11-17 19:04:24 UTC. The
mandatory `--severity HIGH,CRITICAL --exit-code 1` scan failed as required:

| Finding | Package / target | Installed | Fixed | Severity |
|---|---|---:|---:|---|
| CVE-2026-109518 | Ubuntu `apt` | 2.8.3 | 2.8.4ubuntu0.1 | HIGH |
| CVE-2026-109518 | Ubuntu `libapt-pkg6.0t64` | 2.8.3 | 2.8.4ubuntu0.1 | HIGH |
| CVE-2026-111497 | Ubuntu `libbrotli1` | 1.1.0-2build2 | 1.1.0-2ubuntu0.1 | HIGH |
| CVE-2026-114149 | Actions Runner `Microsoft.AspNetCore.WebUtilities` | 8.0.25 | 8.0.34, 9.0.23, 10.0.15 or 11.0.0 | HIGH |
| CVE-2026-78661 | Cosign `golang.org/x/net` | 0.61.0 | 0.62.0 | HIGH |

Result: **5 HIGH, 0 CRITICAL, NO-GO**. Deleting apt executables does not remove
the installed package metadata or `libapt-pkg` library and is not treated as a
security fix. Kubectl has no finding in the complete-image report.

## Evidence checksums

| Evidence | SHA-256 |
|---|---|
| Five-input manifest | `b7c8670b3f573241322c62b740a8a09d10d03759af3e70cf88803b3d403f6a21` |
| BuildKit metadata/provenance | `a3e37c081062395cad9dc5ffa3f494fc07dfc9c51e68014e8e73d0bc249ad700` |
| Trivy JSON | `af481f332107a4f4bbc7b898035a31ef5d194798424180cad679f51e099f2952` |
| Trivy log | `045378b66d33aec96eec56c4f604fee0fbedaa52dfe54390bad36e2633f646d7` |
| Independent SPDX SBOM | `1c64040e77a13047b4b33b4447062425f781f429b625908fa5434846a244ab45` |

Raw artifacts remain under ignored `build/c55-evidence/`; no private path,
credential or raw evidence is committed. The local image is not signed,
published or registry-attested.

## Offline validation status

The Docker build passed checksum, architecture and version checks for all five
inputs. A never-started inspection container proved the embedded kubectl hash
matches and was removed afterward. A negative context containing the preserved
official kubectl 1.35.10 binary failed only `bin/kubectl` in the new checksum
ledger, proving the substitution is rejected. Focused source-policy tests and
shell syntax checks pass.

Runner startup, Helm rendering from inside the runner, Cosign invocation,
manifest validation, kubeconfig access, unauthorized-mutation rejection and
read-only cluster access are **NOT_RUN** because Phase 4 failed. Running those
checks cannot override the mandatory image gate and would violate the required
phase order. No container from this image was started.

## Remaining blockers

The smallest next remediation must independently qualify all of:

1. verified Ubuntu `apt`, `libapt-pkg6.0t64` and `libbrotli1` fixed packages;
2. a maintained compatible Actions Runner containing fixed WebUtilities; and
3. a compatible Cosign build or release with `x/net` 0.62.0 or newer.

After those identities are verified, rebuild the complete runner offline and
repeat the unsuppressed whole-image scan before any runtime test. Publication,
registry digest resolution, signature/attestation, owner approval and the C5
gateway/NetworkPolicy correction remain separate requirements. SEC-022 is
unchanged.
