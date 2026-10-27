#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || -z "${COSIGN_CERTIFICATE_IDENTITY_REGEXP:-}" ]]; then
  echo "usage: COSIGN_CERTIFICATE_IDENTITY_REGEXP=... $0 API_IMAGE@sha256:... KSERVE_IMAGE@sha256:..." >&2
  exit 2
fi

cosign version | grep -q 'GitVersion.*v3.1.4' || { echo "cosign v3.1.4 is required" >&2; exit 2; }
trivy --version | grep -q 'Version: 0.76.1' || { echo "Trivy 0.76.1 is required" >&2; exit 2; }

for image in "$@"; do
  [[ "$image" =~ ^[a-z0-9-]+-docker\.pkg\.dev/[a-z0-9-]+/cogniflow-images/[a-z0-9-]+@sha256:[a-f0-9]{64}$ ]] || {
    echo "invalid Artifact Registry digest reference" >&2
    exit 2
  }
  cosign verify \
    --certificate-identity-regexp "$COSIGN_CERTIFICATE_IDENTITY_REGEXP" \
    --certificate-oidc-issuer https://token.actions.githubusercontent.com \
    "$image" >/dev/null
  trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "$image"
done
