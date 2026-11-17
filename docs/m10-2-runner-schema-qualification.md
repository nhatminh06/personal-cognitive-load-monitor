# M10.2 verified runner artifacts and schema qualification

## Decision and source

**Overall decision: NO-GO.** Kubernetes schema and source-level gates are
`PASS_OFFLINE`. The exact deployment-runner image is `BLOCKED` with two
unsuppressed HIGH findings and therefore is not `PASS_EXACT_IMAGE`. Gateway and
runner Pod behavior remain `NEEDS_RUNTIME`; all cloud activity remains
`NEEDS_OWNER_APPROVAL`.

- Starting commit: `f49ddf2d1bd0c6097751eec2fcae325e23737223`
- Published ancestor: `b7f3ddef1d30eb52e80887d27445c5724a198ce3`
- Branch: `feat/m10-1-security`
- Final commit: the commit containing this report; its exact SHA is recorded in
  the local handoff because a commit cannot contain its own identity.

## Changed files

- `deploy/gke/runners/Dockerfile.deploy`
- `deploy/gke/runners/README.md`
- `deploy/gke/runners/deploy-inputs.SHA256SUMS`
- `docs/cloud-deployment.md`
- `docs/m10-2-runner-schema-qualification.md`
- `docs/module3/gke-gcs-readiness.md`
- `scripts/validate_kubernetes_schemas.py`
- `scripts/verify_cloud_release.sh`
- `src/tests/test_gke_cloud_readiness.py`
- `src/tests/test_kubernetes_schema_validator.py`
- `src/tests/test_m10_release_security.py`

## Historical and current vulnerability baselines

The M10/M10.1 **13 HIGH, 0 CRITICAL** matrix describes the 2026-11-14
historical image only. It is retained in the runner README and was not treated
as a reproduced M10.2 result.

The pinned Actions Runner base was rescanned first with the cached Trivy 0.76.2
database: **36 HIGH, 1 CRITICAL**. Most occurrences came from the base's unused
Node/Docker toolchain, which the deployment Dockerfile already removes. This
count is not comparable to the historical 13 because the exact filesystem and
scan policy differ.

The first M10.2 candidate built with verified Helm 3.22.1 and the full Google
Cloud CLI archive and scanned at **8 HIGH, 0 CRITICAL**. Findings were four
unused bundled pip Python packages, vulnerable optional `gcloud-crc32c`, Helm's
Go runtime, and two kubectl dependencies. Two test private keys shipped in
unused gsutil test fixtures were also detected by secret scanning.

Compatible remediation replaced Helm 3.22.1 with verified Helm 4.3.2 after the
exact chart passed lint/render, and removed unused bq, gsutil, pip, setuptools,
wheel and `gcloud-crc32c` content. The rebuilt exact image has **2 HIGH, 0
CRITICAL**:

| Tool | Finding | Embedded version | Fixed requirement | Status |
|---|---|---|---|---|
| kubectl 1.35.10 | CVE-2026-78669 | `golang.org/x/net` 0.56.0 | 0.60.0 | `BLOCKED`; no newer 1.35 patch exists |
| kubectl 1.35.10 | CVE-2026-56851 | `golang.org/x/text` 0.39.0 | 0.41.0 | `BLOCKED`; no newer 1.35 patch exists |

No exception, ignore file, `--ignore-unfixed`, severity reduction or local fork
was used. The repository cloud-image gate itself still contained
`--ignore-unfixed`; M10.2 removed that defect and updated its exact Trivy check
from 0.76.1 to 0.76.2.

## Verified official runner inputs

Metadata and bytes were retrieved from official HTTPS release locations. Every
artifact was hashed before extraction or execution. Cosign also passed its
official Sigstore bundle with identity
`keyless@projectsigstore.iam.gserviceaccount.com` and issuer
`https://accounts.google.com`.

| Component | Exact identity | Verified artifact SHA-256 | Source / verification |
|---|---|---|---|
| Actions Runner base | 2.338.2, linux/amd64 | image `0ce3288e48b012a83685998f683a2ae0cbd284fa722c090dda0af5443215cf30`; tar `baebf204307bac6193480852732f0aba2ae97b6c5597c244f4d5558390147c40` | official `ghcr.io/actions/actions-runner` digest and GitHub release API digest |
| Cosign | 3.1.4, Go 1.27.3 | `424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa` | official GitHub API digest, checksums file, and Sigstore bundle |
| Helm | 4.3.2, Go 1.27.4 | archive `d1c0278d46beab79582d7e50f5b3dc206944ba8e577cde618513fd07daa53983`; binary `876242ea89b1fc07692e179d9abdc47028979fb64b20d85448e85193c8b04931` | official Helm release checksum; chart lint/render passed |
| kubectl | 1.35.10, Go 1.26.10 | `c49a28f1f4efc4d475ed05f47f2ce8e563bf7bef69ed77fe1b924ea6d83b6327` | `dl.k8s.io` binary and adjacent SHA-256; matches Kubernetes tag commit `ae6fece6…` |
| Trivy | 0.76.2, Go 1.27.3 | archive `bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf`; binary `6a972c69606c7b3ea4c6bdcc6fc9332ea9ad38381624310c1e85cc77345909f3` | official GitHub API digest and release checksums |
| Google Cloud CLI | 594.0.0, linux/x86_64 | `8cf5b2d7987e7aac008264fecda7c083423227ecfb26878707bd20c6219d7dab` | official Google versioned-archive page checksum; mutable rapid URL resolved by verified bytes plus embedded `VERSION=594.0.0` |

`deploy-inputs.SHA256SUMS` records the five exact build-context objects. The
Google archive URL was mutable, so the build additionally asserts its embedded
version and the report records the verified digest. The failed attempt to apply
the page's earlier generic checksum to a 593.0.0 archive was rejected and that
archive was not used.

## Exact image construction and result

Docker 29.9.1 built with `--network=none --pull=false --platform=linux/amd64`
from the immutable Actions Runner base and verified local context. Build-time
hash and version assertions passed.

- Exact local image ID/digest:
  `sha256:dfd51490064d4834bc00cfbddc35f7f151d0c274ccec10270eb45cf790d1cde2`
- Platform: `linux/amd64`
- Runtime identity: UID/GID 1001, with no supplemental privileged groups
- Docker, dockerd, containerd, runc and sudo: absent
- Embedded credentials: none added; unused gsutil test keys removed
- CycloneDX SBOM SHA-256:
  `9a427241ce256ec37b6df0da5dc884167015e6e17930edfea2794fe6bdece89c`
- Trivy JSON SHA-256:
  `a8d93bbc366edeee8e7ca5a7607eb490f36629bb283b5c2a23170d752a0e6224`
- Exact scan: **2 HIGH, 0 CRITICAL**, mandatory exit 1, `BLOCKED`

The local image and generated reports remain outside Git. No registry reference
was created and `SET_DEPLOY_RUNNER_IMAGE` remains unresolved.

## Kubernetes compatibility

| Component | Exact line | Kubernetes 1.35 result |
|---|---|---|
| Kubernetes core / kubectl | 1.35.10 | exact core schema and client line |
| KServe | 0.20.0 Standard | requires Kubernetes 1.32+; structural CRD validation passed |
| Knative Serving/Eventing | 1.23.0 | minimum Kubernetes 1.34; structural CRD validation passed |
| Gateway API | 1.4.0 standard | schema acquired; no Gateway/HTTPRoute is currently rendered |
| External Secrets Operator | 2.13.0 | ExternalSecret and SecretStore schemas passed |
| cert-manager | 1.21.2 | supports/tests Kubernetes 1.35; schema acquired; no cert-manager CR is currently rendered |
| cert-manager historical plan | 1.18.2 | rejected: EOL and supports only Kubernetes 1.29–1.33 |

This corrects the stale GKE readiness table without changing completed Module I
qualification evidence. No ingress-nginx resource was restored.

## Schema bundle and validation

All release assets were checked against official GitHub API digests. Kubernetes
OpenAPI came from the official 1.35.10 tag commit `ae6fece6…`.

| Schema source | SHA-256 |
|---|---|
| Kubernetes 1.35.10 OpenAPI | `483500149ee52ce5753d75f5639101d985bb4f5e902cc05b1ba7627465d62446` |
| KServe 0.20.0 CRDs | `dd5fad5999862c34dde061c97e49419810034320e1245ce9c6e4bfd51cac6255` |
| Knative Serving 1.23.0 CRDs | `b172ff4901ed50f8e4e09ff8616e54d22e264df7086ce8cb74f513a04812fe74` |
| Knative Eventing 1.23.0 CRDs | `20da395bc5a1de2633907d229180a1db3dd4a53fae541c24c6719de0adba8fb8` |
| Gateway API 1.4.0 standard | `6a4029e661446d64add866a00ecdc40c14219b68777ab614c5cdaac0adb481f1` |
| cert-manager 1.21.2 CRDs | `262fef78478492cd35b73a1b227106b7802f9c056361d1f561d04b32d751337f` |
| External Secrets 2.13.0 install/CRDs | `84f0890573d61dd9f7007c1772270d98a372248c74c2758be5c34ca863dedfad` |

The new validator matched schemas by actual group/version/kind rather than
substituting built-in schemas. It checked 66 resources across 18 identities,
including Pods, NetworkPolicies, ServiceAccounts, ResourceQuotas,
StorageClasses, KServe InferenceServices, Knative Brokers/Triggers and External
Secrets resources. Result: zero validation errors and zero uncovered GVKs,
`PASS_OFFLINE`. Negative tests reject missing required fields and uncovered
custom resources.

This proves structural OpenAPI correctness only. CEL, admission webhooks,
controller reconciliation, scheduling and runtime behavior remain
`NEEDS_RUNTIME`.

## Manifest and Gateway security

Exact Helm 4.3.2 lint and GKE render passed with nine resources. Application
images remain digest-bound, Services remain `ClusterIP`, runner roots remain
read-only with bounded writable volumes, and no Ingress, Gateway, HTTPRoute,
LoadBalancer, NodePort or ingress-nginx resource is rendered. Configuration
Trivy scans of GKE, Helm, Knative and Terraform report zero HIGH/CRITICAL
misconfigurations.

The external route remains closed by default. TLS termination, managed
certificate lifecycle, IAP, Cloud Armor, health checks, routing ownership and
live NetworkPolicy behavior remain `NEEDS_RUNTIME`.

## Terraform result

Terraform 1.15.9 used a disposable `TF_DATA_DIR`, `-backend=false`,
`-lockfile=readonly`, and the exact locked Google provider 5.45.2 from the local
mirror. `terraform validate` passed and seven mock-provider input tests passed.
No credentials, state, backend, cloud plan or API was used. As in M10.1, the
plugin-dir installation reports `unauthenticated`; signed-package provenance
remains required before cloud planning.

## Regression and security review

- Focused schema/M10/GKE tests: 35 passed.
- Full Python suite and 81% coverage gate: 604 passed, 2 skipped, 5 warnings;
  87.13% coverage.
- Ruff, Actionlint, Helm lint/render, Terraform formatting/validation/tests,
  four Trivy configuration roots, the sanitized-tree Gitleaks scan and Git
  whitespace checks: passed. The exact commit-range scan is recorded after the
  final commit.
- Exact image gate: expected `FAIL` / `BLOCKED`, 2 HIGH and 0 CRITICAL.

No binary, schema bundle, SBOM, vulnerability report, credential, state file,
personal data, private Track B evidence or raw sensitive evidence is committed.
Only hashes, source URLs, code and sanitized conclusions are retained. No new
runtime dependency was added. Existing license files remain unchanged because
upstream binaries were used only in a temporary local image and were not
redistributed; an owner must review the final SBOM/licenses before any future
publication.

## Outstanding dependencies and M11 readiness

M10.2 is not ready for M11 execution. It is ready only for owner review of the
blocked evidence. A compatible official Kubernetes 1.35 kubectl release must
embed `x/net >= 0.60.0` and `x/text >= 0.41.0`, then the exact runner must be
rebuilt and return zero HIGH/CRITICAL findings. The independently verified
schema gate no longer blocks M11.

After a fixed official kubectl artifact exists, the owner can repeat the local
gate without cloud or registry access:

```bash
# Put only independently verified amd64 inputs in this directory.
cp deploy/gke/runners/deploy-inputs.SHA256SUMS /OWNER/VERIFIED/deploy-inputs/SHA256SUMS
(cd /OWNER/VERIFIED/deploy-inputs && sha256sum -c SHA256SUMS)
docker build --network=none --pull=false --platform=linux/amd64 \
  --build-context artifacts=/OWNER/VERIFIED/deploy-inputs \
  -f deploy/gke/runners/Dockerfile.deploy \
  -t cogniflow-deploy-runner:m10-2 .
docker image inspect cogniflow-deploy-runner:m10-2 \
  --format '{{.Id}} {{.Architecture}} {{.Os}} {{.Config.User}}'
trivy image --skip-db-update --skip-check-update \
  --severity HIGH,CRITICAL --exit-code 1 cogniflow-deploy-runner:m10-2
```

Only a zero-finding exact-image result should permit a separately authorized
M11 disposable-cluster qualification. M11 still must test runner bootstrap and
cleanup, admission, controllers, Gateway TLS/auth/rate limits, NetworkPolicy,
storage, event delivery, observability and teardown. No cluster was created in
M10.2.
