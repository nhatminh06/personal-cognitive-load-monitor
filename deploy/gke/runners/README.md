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
not define a deployment-runner image.

## Deployment-runner blockers

The 2026-11-14 exact-candidate scan remains **NO-GO** with 13 HIGH
findings and 0 CRITICAL findings under the mandatory Trivy gate. The historical report was
not committed to this sanitized branch, so its count and matrix are retained
as historical evidence, not rerun evidence. Publication and registration stay
forbidden until an exact rebuilt image reports zero HIGH/CRITICAL findings.

Official release metadata was rechecked on 2026-11-17. Actions Runner 2.338.2
and Cosign 3.1.4 remain current; Helm 3.22.1 remains the current Helm 3 line;
kubectl 1.35.10 and Trivy 0.76.2 exist. These observations are not remediation
evidence: no replacement artifacts were checksum-qualified, embedded dependency
fixes were not assumed, and no exact rebuilt deployment-runner image was scanned.

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

`Dockerfile.deploy` is a fail-closed build scaffold, not an accepted image. It
pins the amd64 runner base, consumes only a preverified local artifact context,
rechecks `SHA256SUMS`, removes the container daemon and privileged memberships,
and runs as UID/GID 1001. The example checksum file deliberately contains
invalid `UNVERIFIED` values. An owner must replace them from official signed or
checksum-qualified provenance and separately record exact versions before this
command is allowed:

```bash
docker build --network=none --pull=false --platform=linux/amd64 \
  --build-context artifacts=/OWNER/VERIFIED/deploy-inputs \
  --file deploy/gke/runners/Dockerfile.deploy \
  --tag cogniflow-deploy-runner:m10-1 .
```

Do not use a cached local image with unknown provenance as the artifact
context. Scan the resulting exact image without suppressions before resolving
`SET_DEPLOY_RUNNER_IMAGE`.
