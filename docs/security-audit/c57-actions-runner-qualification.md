# C5.7 Actions Runner qualification

**Qualification date:** 2026-11-17  
**Decision:** **PASS** (independent Actions Runner package only)

No fixed official release was available. The latest official release remained
`v2.338.2` at signed tag commit
`d1eb12d4b115c301201de27d667284e1a80f2ab5`; its Linux x64 archive SHA-256 is
`baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40` and it
contains vulnerable `Microsoft.AspNetCore.WebUtilities` 8.0.25.

The qualified package was built from the signed, merged upstream WebUtilities
8.0.34 change at commit `a9dcf1bf7a78751648ff630fd4d0152471293487`.
The verified source archive SHA-256 is
`a0e02e28a079609da2682b962e7d05468c6b345e19b16e7c24cda4e6aed9263d`.
It reports runner version `2.338.0`; it is a local source candidate, not an
official `v2.338.2` release.

## Immutable build inputs and result

- Microsoft .NET SDK/runtime: 8.0.428 / 8.0.34
- SDK archive SHA-256:
  `6f8b64ef9644b11bcab6748ebfec088d2ae4868df26204bb2354c3ada0f09cbe`
- Node Linux x64: 24.22.3, SHA-256
  `061ec3e3062115705b56b51fa9cc330ab50d34b6969387d4e4b1a50c6809acc2`
- Node Alpine x64: 24.22.3, SHA-256
  `07fae3d6173ae8bc6529df8a4b3c070d80f94e95bd816982c4af253acf7c2b51`
- Qualified archive: `actions-runner-linux-x64-a9dcf1b-cogniflow.tar.gz`
- Archive SHA-256:
  `6d552c6b6acf854247f0b4c439586dd53196f54b94ba8320c76696d6a18d2e46`

Two deterministic packaging runs produced the same archive digest. The
production layout contains WebUtilities 8.0.34, Node 24.22.3, the listener,
worker, configuration/startup scripts and the bundled `hashFiles` action.

## Upstream test diagnosis and result

The retained C5.6 Release run reported 1,161 passed and three failures:

| Test | Diagnosis | Minimum correction |
|---|---|---|
| `HostContextL0.AuthMigrationAutoReset` | Test-only refresh override is compiled under `#if DEBUG`; Release cannot honor its one-second expectation. | Run the upstream suite in its intended Debug configuration. |
| `RunnerL0.TestReportAuthMigrationTelemetry` | Same Debug-only refresh override and timeout mismatch. | Run the upstream suite in Debug. |
| `ProcessExtensionL0.SuccessReadProcessEnv` | The test called `GetProcessById` once, which succeeds before Node finishes `exec`, then read `/proc/<pid>/environ` after 1–3 ms. | Poll for the expected value for at most five seconds; keep the assertion. |

The first unchanged Debug run passed 1,164/1,165 and exposed only the process
environment race. A second unchanged run also exposed that race; its additional
self-update failure was caused by `/tmp` reaching 98% while extracting the
official 217 MB runner archive (`No space left on device`). Redirecting temporary
files to persistent workspace storage made that test pass without changing it.

The test-only process race correction neither skips nor relaxes the assertion;
its patch SHA-256 is
`eefb992d9f2ec135f821327d4fff9bdd65d538b6eec59ea73557807f1e8b21a5`.
With that correction, the complete suite passed: **1,165 passed / 0 failed / 0
skipped**. No production source was changed by the test correction.

## Node/npm packaging review

The untrimmed upstream Node distribution reported **28 HIGH / 1 CRITICAL**,
entirely in the bundled npm/corepack dependency tree. The critical finding was
`tar` 6.2.1 (`CVE-2026-59873`); HIGH findings included vulnerable `tar`,
`brace-expansion`, `cross-spawn`, `glob`, `minimatch`, `pacote`, `sigstore` and
`undici` versions.

Repository and layout inspection found no runner lifecycle reference to npm,
npx or corepack. Actions Runner executes the Node binary and its pre-bundled
`bin/hashFiles/index.js`; both remain. Packaging therefore excludes only
`externals/node24/lib/node_modules`. It does not remove the Node executable,
the Alpine Node runtime, `hashFiles`, licenses, listener, worker or scripts.

## Security and offline compatibility

Trivy 0.76.2 scanned the exact extracted archive with schema-2 vulnerability
and Java databases updated 2026-11-17. All seven detected .NET dependency
manifests were covered: **0 HIGH / 0 CRITICAL**, with no scan error or
suppression. Evidence SHA-256 values:

- Trivy JSON: `98c82f76910cba0f561f3eb250a4bceefeba72c15483cdc79ec58763d7e34138`
- SPDX JSON (383 packages):
  `9c5860bc02e0ea20cbbe24a41ea46b9648370664c1c45fb2e1deacd01c2cccad`

Offline checks passed for listener version/help, configuration help, Node
version, executable listener/worker/start scripts, `hashFiles`, and the exact
package inventory. No runner was registered, no job was accepted, and no
Kubernetes or cloud API was mutated.

## Boundary and next step

This PASS qualifies the independent Actions Runner package only. It does not
qualify or authorize the complete M10.3 deployment runner. The exact next step
is to rebuild that image from the C5.6 authenticated Ubuntu packages, qualified
Cosign `v3.1.4-cogniflow.1`, qualified kubectl
`v1.35.10-cogniflow.1`, and this exact archive; then independently verify its
embedded hashes, SBOM, provenance, zero-HIGH/zero-CRITICAL whole-image scan and
offline runner tests. Registry publication, signing/attestation, owner approval
and environment-specific deployment gates remain separate. M10.3 remains
NO-GO and SEC-022 is unchanged.
