# C16 controller image qualification

**Date:** 2026-11-19

**Starting revision:** `6cb6bf353726c8465861daecde9191aa008dc6ee`

**Decision:** **PARTIAL — KFP database image blocks the first runtime stage**

No Kubernetes object, protected cluster, cloud resource, registry, or model was
changed. Seven mandatory KFP/Argo images are locally security-qualified, but
they are not published, signed, attested, or live-runtime-qualified.

## Selected release family and actual inventory

The selected coherent family is KFP `2.18.1` at verified commit
`7dd28116ad652bfb7b6c282e7920be84e6a7634a`, Argo Workflows `4.1.6` at
verified commit `43021573c5a35cbafae009043c132dfcef43a112`, the KFP PostgreSQL overlay,
and SeaweedFS `4.54`. KFP SDK `2.17.3` remains compatible with the v2 API and
the existing six-component pipeline still compiles.

The upstream manifests require more than the former role ledger exposed. A
headless six-component run needs these image roles:

| Role | Exact selected identity | C16 result |
|---|---|---|
| API server | local `sha256:d70accf…859ad` | 0 HIGH / 0 CRITICAL |
| Persistence agent | local `sha256:707c3af5…a68dc` | 0 / 0 |
| Scheduled-workflow controller | local `sha256:9fa52c2f…491f3` | 0 / 0 |
| Workflow controller | local `sha256:c115303d…b44fd` | 0 / 0 |
| Workflow executor (`argoexec`) | local `sha256:f597b170…15802` | 0 / 0 |
| KFP driver | local `sha256:175b9bbf…f963` | 0 / 0 |
| KFP launcher | local `sha256:8e2f3860…ad9c5` | 0 / 0 |
| Init/wait container | `alpine:3.23.8@sha256:469c9ea4…971eb2` | not reached |
| Metadata writer | `ghcr.io/kubeflow/kfp-metadata-writer:2.18.1` | digest/scan not reached |
| Metadata Envoy | `ghcr.io/kubeflow/kfp-metadata-envoy:2.18.1` | digest/scan not reached |
| ML Metadata gRPC | `gcr.io/tfx-oss-public/ml_metadata_store_server:1.14.0` | digest/scan not reached |
| PostgreSQL | `postgres:18.7-alpine3.23@sha256:e6014245…24f1` | **1 CRITICAL / 26 HIGH** |
| SeaweedFS | `ghcr.io/chrislusf/seaweedfs:4.54@sha256:4b42c212…2d15` | not reached |
| CogniFlow component image | immutable runtime input | retained; publication still required |
| MLflow | isolated registry image | still unqualified |

The full upstream installation additionally includes cache server/deployer,
frontend/signing-key job, viewer controller, and visualization server images.
The existing pipeline disables caching on all six components and does not need
the UI/viewer/visualization services for a headless run, but that reduced
overlay has not received live compatibility acceptance. The C11 ledger now
explicitly requires driver, launcher, executor, metadata, database, and init
roles so those dependencies cannot disappear behind controller-only claims.

## Qualified local images

Trivy `0.76.2` used schema-2 database timestamp
`2026-11-19T01:05:40.842299544Z`, with `/dev/null` as the ignore file. Each
scan covered OS and embedded language dependencies. SPDX JSON SBOMs and raw
scan hashes are recorded in
[`assessment.json`](c16-evidence/assessment.json).

- The C14 API server was rescanned against the current database and retained
  0 HIGH / 0 CRITICAL, non-root `65532:65532`, and its exact source identity.
- Persistence agent, scheduled-workflow controller, driver, and launcher used
  the KFP `2.18.1` source/binaries with the unsupported Alpine `3.21` runtime
  replaced by digest-pinned supported Alpine `3.23.8`. Their binary help checks
  passed and all run as `65532:65532`.
- Workflow controller and `argoexec` were rebuilt together from verified Argo
  `4.1.6` source using Go `1.27.4`, `go-jose` `4.1.6`, and `x/net` `0.62.0`.
  Version checks passed; both run as `8737:8737` and scan at 0 HIGH / 0 CRITICAL.

These are exact **local image IDs**, not published OCI repository digests. No
signature or SLSA attestation was fabricated. The KFP release tag is unsigned;
the recorded upstream KFP and Argo commits have valid GitHub signatures.

## Mandatory blocker and stop decision

The exact PostgreSQL image pinned by KFP's PostgreSQL installation path uses a
supported Alpine `3.23.8` base, but `/usr/local/bin/gosu` `1.19` embeds Go
`1.24.6`. The complete scan reports 1 CRITICAL and 26 HIGH findings, including
the Go standard-library fixes required through Go `1.27.4`.

The one permitted remediation attempted to rebuild the same gosu version with
Go `1.27.4`. It failed before producing an image because the repository does
not publish a `v1.19` Go module tag. C16 therefore stopped this stack without a
second database approach. Metadata, SeaweedFS, MLflow, KServe, and Knative
qualification did not proceed.

## Resources and boundaries

Immediately before the first build, available memory was `6,665,265,152`
bytes. Final available memory was `8,463,310,848` bytes, swap use was
`5,648,465,920` bytes, persistent free space was `110,210,437,120` bytes, and
`/tmp` had `5,904,842,752` bytes free. Docker reported 132.3 GB of images and
83.6 GB of build cache. Nothing was pruned or stopped. The two retained kind
control-plane containers remained running and were never queried or mutated.

## Remaining unblock requirements

1. Establish one reviewed, reproducible gosu/PostgreSQL remediation or select a
   supported database image whose complete scan is 0 HIGH / 0 CRITICAL.
2. Qualify the remaining metadata, init, SeaweedFS, MLflow, and component
   images by exact digest.
3. Publish the accepted local builds under immutable OCI digests, then produce
   real signatures, SPDX attestations, and provenance attestations.
4. Render an immutable reduced KFP overlay and perform separately authorized
   isolated startup, readiness, API, artifact, authorization, and failure tests.
5. Only after KFP passes may C16 advance to KServe and then durable Knative
   Eventing qualification.

This partial result does not authorize cluster creation, deployment, registry
publication, model approval, or cloud access.

## Validation

- Focused C10/C11, image-evidence, deployment-gate, pipeline, and release
  security tests: 66 passed.
- Full regression: 675 passed, 2 skipped, 5 warnings; combined coverage 87%.
- KFP PostgreSQL manifest render: 79 resources; SHA-256
  `feb63a155941cd109f4324f0b20368449f33c9a5bc523aee967da93e99b86eaf`.
- C11 acceptance wrapper: expected `BLOCKED` exit 3, with
  `mutation_executed=false` and missing authorization/evidence gates retained.
- Ruff, scoped MyPy, JSON validation, shell syntax, Helm lint/render, and Git
  whitespace checks passed.
