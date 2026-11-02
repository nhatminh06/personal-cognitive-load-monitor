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

| Binary | Finding | Fixed component version | Review when |
|---|---|---|---|
| Cosign 3.1.4 | CVE-2026-111943 | Go 1.27.3 | A newer official Cosign release embeds the fix |
| Cosign 3.1.4 | CVE-2026-78667 | Go 1.27.2 | A newer official Cosign release embeds the fix |
| Cosign 3.1.4 | CVE-2026-78669 | Go 1.27.2 | A newer official Cosign release embeds the fix |
| Cosign 3.1.4 | CVE-2026-97031 | Go 1.27.2 | A newer official Cosign release embeds the fix |
| Helm 3.22.1 | CVE-2026-111943 | Go 1.26.10 or 1.27.3 | A newer official Helm release embeds the fix |
| kubectl 1.34.13 | CVE-2026-78669 | `golang.org/x/net` 0.60.0 | A GKE-1.34-compatible official kubectl release embeds the fix |
| kubectl 1.34.13 | CVE-2026-56851 | `golang.org/x/text` 0.41.0 | A GKE-1.34-compatible official kubectl release embeds the fix |
| Trivy 0.76.1 | CVE-2026-116587 | `go-jose/v4` 4.1.6 | A newer official Trivy release embeds the fix |
