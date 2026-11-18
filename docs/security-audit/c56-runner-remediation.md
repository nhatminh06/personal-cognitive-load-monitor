# C5.6 final runner vulnerability remediation

**Qualification date:** 2026-11-17  
**Decision:** **BLOCKED**

The three required remediation paths were evaluated independently. Authenticated
Ubuntu packages and a source-built Cosign candidate passed their standalone
checks. No official fixed Actions Runner release exists, and the bounded source
candidate did not complete compatibility qualification. Consequently the C5.5
runner was not rebuilt, started, published or used against Kubernetes. M10.3
remains NO-GO and SEC-022 is unchanged.

## Preserved C5.5 identity

- Source starting commit: `de4514f4c61ac2239fdd8a8425a0d53105a2ba5d`
- Preserved runner image:
  `sha256:073432d2da9a1c4ceb18ca7d3654984fbed88635d207ab59407b65c01f70d8a7`
- Qualified kubectl: `v1.35.10-cogniflow.1`
- Kubectl SHA-256:
  `130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef`

The preserved image was rescanned with Trivy 0.76.2 and database schema 2
updated `2026-11-17 19:04:24 UTC`. Its result remains exactly **5 HIGH / 0
CRITICAL**. No C5.5 input, image or rollback identity was overwritten.

## Authenticated Ubuntu packages: PASS

The Ubuntu Noble Updates and Noble Security `InRelease` files were verified by
`gpgv` against the archive keyring extracted from the pinned C5.5 base. Both
signatures chain to Ubuntu Archive Automatic Signing Key 2018 fingerprint
`F6ECB3762474EDA9D21B7022871920D1991BC93C`. Package hashes came from the
signed `Packages.xz` indexes and matched the downloaded files.

| Package | Fixed version | SHA-256 |
|---|---|---|
| `apt` | `2.8.4ubuntu0.1` | `ad2ea7f107f250ba88b0bfdba31812a341e3247589647aa2b03b9dc4e8abf8ed` |
| `libapt-pkg6.0t64` | `2.8.4ubuntu0.1` | `a50f3e68a793f90b05f44a4b5f2f59f3ec7687e39b5d8bbd1da44c84671fa3d6` |
| `libbrotli1` | `1.1.0-2ubuntu0.1` | `70b188a86d81f30d7510aab30e25d638ed5037dded6691af1533952b71ac61de` |

The control metadata confirms amd64 architecture and compatible Noble runtime
dependencies. These artifacts were not integrated because the Actions Runner
prerequisite failed.

## Cosign source candidate: PASS standalone

The latest official release remained v3.1.4 with vulnerable `x/net` 0.61.0.
The verified annotated tag resolves to commit
`0e48502cf5ef34e2e60bbd3617aa19945712f705`; its source archive SHA-256 is
`9d57a78b666ace26c7184b14ba1b1e7f5177df2c5ca1c24e4ea12e3ca847922b`.
Go 1.27.4 built `v3.1.4-cogniflow.1` with only `x/net` advanced to 0.62.0. The
resulting binary SHA-256 is
`67a3ba89c77e654c3b3fe9507817ef9c3a3b802c7363781158f2ecf62bf5d901`.

- Current Trivy Go-binary scan: **0 HIGH / 0 CRITICAL**, complete, no error
- Trivy JSON SHA-256:
  `64c3c8c3e107d9914fe0e64b3344791a9c40e4ce68d84f551bbd3a717c8c6a30`
- SPDX JSON SHA-256:
  `6d85480482ad207f927bed7eedb85f866c96a0ab38f7d69272d0eef95d7a2edd`
- Signature-verification smoke test: `Verified OK` against the official v3.1.4
  Sigstore bundle and expected `keyless@projectsigstore.iam.gserviceaccount.com`
  identity

This is a local source candidate, not a published or signed Sigstore release.

## Actions Runner source candidate: BLOCKED

The latest official Actions Runner remains 2.338.2, archive SHA-256
`baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40`,
and still contains WebUtilities 8.0.25. The exact official tag commit is
`d1eb12d4b115c301201de27d667284e1a80f2ab5`; the retained source archive
SHA-256 is
`a0fa836ec067173a6de1d5afc1ae7c9f5e23cd576884385d6d020c7a529c6e5e`.

A bounded source experiment used Microsoft's authenticated .NET 8.0.428 SDK
(runtime 8.0.34) and a direct same-major WebUtilities 8.0.34 override. The SDK
archive matched Microsoft's SHA-512 release metadata; its SHA-256 is
`6f8b64ef9644b11bcab6748ebfec088d2ae4868df26204bb2354c3ada0f09cbe`.
The resulting listener reports 2.338.2, and the restored dependency graph
contains WebUtilities 8.0.34 rather than 8.0.25.

The upstream suite did not pass: **1,161 passed / 3 failed / 0 skipped**. The
failures were `AuthMigrationAutoReset`, `SuccessReadProcessEnv`, and
`TestReportAuthMigrationTelemetry`. They appear environment-sensitive, but
were not waived or relabeled as passes. The untrimmed layout scan also reports
**28 HIGH / 1 CRITICAL** in npm bundled with the upstream Node distributions.
The established final Dockerfile removes those unused npm trees, but no
inference from that later transformation is accepted as qualification of this
source candidate.

Because compatibility did not pass independently, no custom Actions Runner
archive was admitted into the offline artifact inventory. No final image ID,
whole-image SPDX SBOM, provenance statement or runtime acceptance result exists
for C5.6.

## Deferred checks and exact next step

Runner startup, embedded-tool assertions, Helm rendering, kubeconfig isolation,
read-only API access and unauthorized-mutation rejection are **NOT_RUN** because
the source-runner prerequisite failed. No Kubernetes API traffic occurred.

The smallest next step is to consume an official Actions Runner release that
contains WebUtilities 8.0.34 or newer, verify its official archive checksum,
then combine it with the three authenticated Ubuntu packages and the qualified
Cosign candidate in a fresh offline build. If a custom source runner remains
necessary, first reproduce and resolve the three upstream test failures and
scan the exact npm-stripped package before changing the tracked runner build.
Only then may the complete image be rebuilt and subjected to the mandatory
zero-HIGH/zero-CRITICAL gate.
