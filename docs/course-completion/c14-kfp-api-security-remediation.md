# C14 targeted KFP API Server security remediation

**Date:** 2026-11-18. **Starting revision:**
`4d20c15223b1670eea9f2a5b100302c2c90367d8`. **Decision:** **BLOCKED**.

The bounded source build produced a security-qualified KFP 2.18.1 API Server,
but the task restrictions prevented the Kubernetes API access required to reach
readiness and complete live compatibility tests. Neither retained kind cluster
was queried or mutated. No production dependency matrix, registry, model,
scanner metadata, or security exception changed.

## C13 finding classification

The original report checksum was reverified as
`bf72aa5b8fe847bd2d94972da27c52df122bb3c4744640faea4e813c4d35763d`.
Its 95 gate findings divide into 68 operating-system findings and 27 findings
inside `usr/bin/apiserver`, a Go executable. There are no Python, JavaScript,
Java, or unsupported-runtime findings.

| Origin | Directness | HIGH | CRITICAL | Remediation |
|---|---|---:|---:|---|
| Debian base layer | Transitive base-image packages | 60 | 3 | Minimal runtime replacement |
| Image-installed `wget`/OpenSSL layer | Direct image dependencies | 5 | 0 | Removed from runtime; HTTP probes need no executable |
| Go toolchain/stdlib 1.26.3 | Toolchain | 15 | 0 | Go 1.27.4 |
| Go modules | 7 direct, 5 transitive | 12 | 0 | KFP 2.18.1 module lock |

The Go module findings were Argo Workflows, go-jose, klauspost/compress,
`x/crypto`, `x/net`, `x/text`, and gRPC. KFP 2.18.1 pins versions at or above
the scanner fixes, including Argo 4.1.6, go-jose 4.1.9, compress 1.20.3,
`x/crypto` 0.59.0, `x/net` 0.62.0, `x/text` 0.44.0, and gRPC 1.85.0.
The complete per-CVE ledger is [findings.csv](c14-evidence/findings.csv).

A base-image-only repair of 2.17.2 would still leave all 27 embedded Go
findings and the shared-pipeline upload authorization flaw fixed in 2.18.0.
The supported release upgrade was therefore required.

## Supported release and compatibility

KFP 2.18.1 source commit
`7dd28116ad652bfb7b6c282e7920be84e6a7634a` has a valid GitHub commit
signature. The annotated tag object itself is not signed, so provenance relies
on the verified commit plus the source archive SHA-256
`49da3fcb824ece95335140f1252672257b4d47bb99f7c4f5b093428a1a5667ce`.

Upstream API CI covers Kubernetes 1.33.12 and 1.36.1 and both Argo 3.7.18 and
4.1.6. The upstream compatibility policy supports KFP v2 SDKs with a v2
runtime. The existing CogniFlow SDK 2.17.3 compiled the six-component pipeline
unchanged, including immutable component images, non-root task settings, and
the existing artifact importers. The server upgrade does not change component
images, MLflow candidate-only registration, approval controls, or previously
compiled pipeline packages. KFP 2.18.1 retains S3-compatible artifact handling
and its manifests include SeaweedFS configuration.

The production dependency matrix remains unchanged pending a live qualification.

## Bounded source build and security result

[Dockerfile.c14-kfp-api](../../Dockerfile.c14-kfp-api) uses the digest-pinned
upstream Go 1.27.4 builder, the verified KFP 2.18.1 source and module sums, the
digest-pinned official release only for compiled sample assets, and the
digest-pinned non-root Debian 13 distroless runtime. The resulting binary is
reproducible with `-trimpath`, no VCS probing, an empty build ID, and locked Go
modules. It runs as UID/GID 65532.

| Image | Exact local identity | HIGH | CRITICAL | Scan SHA-256 |
|---|---|---:|---:|---|
| Official 2.18.1 | `sha256:d896bf8eaa224f5ba005d72a7f865b51a680e36e4ffc8a265623098f1b6b9c2f` | 48 | 0 | `2d9b9b21f7d378e5a11fe7b24e2a7975a6e0afb22a32a2a53d6e9f6f1c32b464` |
| C14 source build | `sha256:d70accf415ef407fd23fd7a790cfd8f9ec9877324018434264fdb66d378859ad` | **0** | **0** | `1846f43885390ce74548e828e2002105273d71e1c26e6f8d83b0a2b23ae7c156` |

The source-build scan was complete and unsuppressed. It reported 19 MEDIUM,
8 LOW, and 8 UNKNOWN findings; none trigger the existing gate. Scanner metadata
was not edited.

## Functional and resource results

- Existing CogniFlow pipeline and task tests: 20 passed, with one existing
  MLflow/SQLAlchemy warning. This covers the six-component graph, immutable
  component identity, MLflow candidate registration, and approval status.
- Focused upstream upload-authorization tests passed, including shared-pipeline
  allow/deny cases and infrastructure-error redaction.
- The candidate binary launched as non-root and exposed its expected API flags.
- In a task-owned Docker network, MySQL 8.4 initialized and API schema migration
  completed. With no Kubernetes API, the server did not bind its HTTP ports and
  failed closed after the configured five-second dependency timeout.
- Health, readiness, live SDK calls, live SeaweedFS artifact access, and live
  authentication boundaries were not claimed because readiness was not reached.

Available memory was 6,870,614,016 bytes before the build, above the adopted
6 GiB local gate. After the build it was 8,814,018,560 bytes; persistent and
`/tmp` free space were 123,553,087,488 and 8,041,943,040 bytes. During the
isolated startup, the API used 20.84 MiB and MySQL used 658.1 MiB.

## Remaining blocker

The exact unresolved prerequisite is an isolated Kubernetes API and the KFP
CRDs/controllers needed by API Server initialization. Creating or mutating that
environment is prohibited by this task, and neither protected cluster may be
used. A future authorized qualification must run this exact local image in a
task-owned Kubernetes environment, verify readiness and the selected SDK,
exercise SeaweedFS artifacts and authentication/authorization failures, then
rebuild once more to confirm reproducibility before changing the production
matrix. No remaining KFP controller rebuild was started.

Machine-readable evidence is in
[assessment.json](c14-evidence/assessment.json). C6 and SEC-022 remain unchanged.
