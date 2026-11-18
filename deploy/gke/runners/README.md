# Private packaging runner

`Dockerfile.release` builds the Linux/amd64 `cogniflow-release` runner used only
by the protected private-MLflow packaging job. It derives from the immutable
official Actions Runner 2.338.2 amd64 manifest, applies the checksum-pinned
Ubuntu `libbrotli1` security update, and removes Docker, containerd, runc,
Buildx, sudo and unused npm/corepack files. Runtime UID/GID remains 1001.

Prepare the verified package outside the build, resolve the pinned base into the
trusted local cache, then build without network access:

```bash
deploy/gke/runners/prepare-release-inputs.sh /tmp/cogniflow-release-inputs
docker build --network=none --pull=false --platform=linux/amd64 \
  --build-context packages=/tmp/cogniflow-release-inputs \
  --file deploy/gke/runners/Dockerfile.release \
  --tag cogniflow-release-runner:local .
```

The pinned Python and uv setup actions install the packaging runtime during the
job. Do not replace `SET_RELEASE_RUNNER_IMAGE` until a separately authorized
publication is scanned and its registry linux/amd64 manifest digest is verified.
`SET_DEPLOY_RUNNER_IMAGE` remains unresolved; this directory intentionally does
not define an accepted deployment-runner image.

## Deployment-runner blockers

C5.5 replaced only the vulnerable upstream kubectl in the M10.2 candidate with
the independently qualified `v1.35.10-cogniflow.1` binary. The old runner image
`sha256:dfd51490064d4834bc00cfbddc35f7f151d0c274ccec10270eb45cf790d1cde2`
is preserved. The rebuilt exact local image is
`sha256:073432d2da9a1c4ceb18ca7d3654984fbed88635d207ab59407b65c01f70d8a7`.
Its current unsuppressed whole-image Trivy scan reports **5 HIGH, 0 CRITICAL**:
Ubuntu `apt`, `libapt-pkg6.0t64`, and `libbrotli1`; Actions Runner's
`Microsoft.AspNetCore.WebUtilities`; and Cosign's `golang.org/x/net`. Kubectl
has no remaining HIGH/CRITICAL finding. The image remains `NO-GO`, must not be
published, and must not replace `SET_DEPLOY_RUNNER_IMAGE`.

The candidate uses Actions Runner 2.338.2, Cosign 3.1.4, Helm 4.3.2, qualified
kubectl `v1.35.10-cogniflow.1`, Trivy 0.76.2, and Google Cloud CLI 594.0.0.
`deploy-inputs.SHA256SUMS` records the exact build-context bytes and
`build-qualified-kubectl.sh` reconstructs kubectl from authenticated upstream
source before enforcing its final digest. Helm 4.3.2 passed this chart's lint
and GKE render paths; cluster behavior remains unverified. Unused gcloud
pip/setuptools tooling, gsutil, bq and `gcloud-crc32c` are removed. Docker,
containerd, runc, sudo and their privileged groups remain absent.

Build from the five independently verified files only:

```bash
cp deploy/gke/runners/deploy-inputs.SHA256SUMS /OWNER/VERIFIED/deploy-inputs/SHA256SUMS
(cd /OWNER/VERIFIED/deploy-inputs && sha256sum -c SHA256SUMS)
docker build --network=none --pull=false --platform=linux/amd64 \
  --build-context artifacts=/OWNER/VERIFIED/deploy-inputs \
  --file deploy/gke/runners/Dockerfile.deploy \
  --tag cogniflow-deploy-runner:c55-qualified .
trivy image --skip-db-update --skip-check-update \
  --severity HIGH,CRITICAL --exit-code 1 cogniflow-deploy-runner:c55-qualified
```

The final command currently fails on the five independently recorded findings.
Do not suppress them or infer that kubectl's standalone pass qualifies the
whole image.

### Historical M10/M10.1 evidence

The 2026-11-14 exact-candidate scan remains **NO-GO** with 13 HIGH
findings and 0 CRITICAL findings under the mandatory Trivy gate. The historical report was
not committed to this sanitized branch, so its count and matrix are retained
as historical evidence, not rerun evidence. Publication and registration stay
forbidden until an exact rebuilt image reports zero HIGH/CRITICAL findings.

These 13 rows describe the older image only. They are not the finding count for
the M10.2 candidate and are retained for audit history.

| Component | CVE | Severity | Vulnerable dependency/version | Official fixed version | Candidate | Evidence | Status / blocker |
|---|---|---|---|---|---|---|---|
| Ubuntu `apt` | CVE-2026-109518 | HIGH | `apt` 2.8.3 | 2.8.4ubuntu0.1 | UNVERIFIED | 2026-11-14 exact scan | BLOCKED: package artifact not verified |
| Ubuntu `libapt-pkg6.0t64` | CVE-2026-109518 | HIGH | 2.8.3 | 2.8.4ubuntu0.1 | UNVERIFIED | 2026-11-14 exact scan | BLOCKED: package artifact not verified |
| Actions Runner 2.338.2 | CVE-2026-114149 | HIGH | `Microsoft.AspNetCore.WebUtilities` 8.0.25 | 8.0.34, 9.0.23, 10.0.15, or 11.0.0 | none verified | 2026-11-14 exact scan | BLOCKED: no official replacement runner verified |
| Cosign 3.1.4 | CVE-2026-78661 | HIGH | `golang.org/x/net` 0.61.0 | 0.62.0 | none verified | 2026-11-14 exact scan | BLOCKED: no official replacement artifact verified |
| Helm 3.22.1 | CVE-2026-78661 | HIGH | `golang.org/x/net` 0.60.0 | 0.62.0 | none verified | 2026-11-14 exact scan | BLOCKED: Helm 4 is not a compatible drop-in |
| Helm 3.22.1 | CVE-2026-111943 | HIGH | Go 1.26.9 | 1.26.10 or 1.27.3 | none verified | 2026-11-14 exact scan | BLOCKED: replacement Helm 3 artifact not verified |
| kubectl 1.35.9 | CVE-2026-78661 | HIGH | `golang.org/x/net` 0.56.0 | 0.62.0 | 1.35.10 UNVERIFIED | 2026-11-14 exact scan | BLOCKED: candidate dependency fix not established |
| kubectl 1.35.9 | CVE-2026-78669 | HIGH | `golang.org/x/net` 0.56.0 | 0.60.0 | 1.35.10 UNVERIFIED | 2026-11-14 exact scan | BLOCKED: candidate dependency fix not established |
| kubectl 1.35.9 | CVE-2026-56851 | HIGH | `golang.org/x/text` 0.39.0 | 0.41.0 | 1.35.10 UNVERIFIED | 2026-11-14 exact scan | BLOCKED: candidate dependency fix not established |
| kubectl 1.35.9 | CVE-2026-111943 | HIGH | Go 1.26.8 | 1.26.10 or 1.27.3 | 1.35.10 UNVERIFIED | 2026-11-14 exact scan | BLOCKED: embedded Go fix not established |
| kubectl 1.35.9 | CVE-2026-78667 | HIGH | Go 1.26.8 | 1.26.9 or 1.27.2 | 1.35.10 UNVERIFIED | 2026-11-14 exact scan | BLOCKED: embedded Go fix not established |
| kubectl 1.35.9 | CVE-2026-78669 | HIGH | Go 1.26.8 | 1.26.9 or 1.27.2 | 1.35.10 UNVERIFIED | 2026-11-14 exact scan | BLOCKED: embedded Go fix not established |
| kubectl 1.35.9 | CVE-2026-97031 | HIGH | Go 1.26.8 | 1.26.9 or 1.27.2 | 1.35.10 UNVERIFIED | 2026-11-14 exact scan | BLOCKED: embedded Go fix not established |

The example checksum file remains a deliberately invalid template. Do not use
it, or a cached local image with unknown provenance, for qualification.
