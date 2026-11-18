#!/usr/bin/env bash
set -euo pipefail

readonly requested_output_dir="${1:?usage: $0 OUTPUT_DIRECTORY}"
readonly version="v1.35.10"
readonly source_sha512="21206f71aa990caced61df7b5851a04c302e72ec61768ac95dd694e37ec8517f59abefe0fa782bf5bf4398014a777c1524524c291e5a97f55b834cc5af034bf9"
readonly go_sha256="7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840"
readonly binary_sha256="130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef"
readonly work_dir="$(mktemp -d "${TMPDIR:-/tmp}/cogniflow-kubectl.XXXXXX")"
cleanup() {
  chmod -R u+w "$work_dir" 2>/dev/null || true
  rm -rf -- "$work_dir"
}
trap cleanup EXIT

for command in cosign curl sha256sum sha512sum tar; do
  command -v "$command" >/dev/null || { echo "$command is required" >&2; exit 2; }
done

mkdir -p "$requested_output_dir/bin" "$work_dir/source" "$work_dir/cache"
readonly output_dir="$(cd "$requested_output_dir" && pwd)"
curl --fail --location --proto '=https' --tlsv1.2 \
  "https://dl.k8s.io/${version}/kubernetes-src.tar.gz" \
  --output "$work_dir/kubernetes-src.tar.gz"
curl --fail --location --proto '=https' --tlsv1.2 \
  "https://dl.k8s.io/${version}/kubernetes-src.tar.gz.sig" \
  --output "$work_dir/kubernetes-src.tar.gz.sig"
curl --fail --location --proto '=https' --tlsv1.2 \
  "https://dl.k8s.io/${version}/kubernetes-src.tar.gz.cert" \
  --output "$work_dir/kubernetes-src.tar.gz.cert"
curl --fail --location --proto '=https' --tlsv1.2 \
  https://go.dev/dl/go1.27.4.linux-amd64.tar.gz \
  --output "$work_dir/go.tar.gz"

echo "$source_sha512  $work_dir/kubernetes-src.tar.gz" | sha512sum --check --strict -
echo "$go_sha256  $work_dir/go.tar.gz" | sha256sum --check --strict -
cosign verify-blob "$work_dir/kubernetes-src.tar.gz" \
  --signature "$work_dir/kubernetes-src.tar.gz.sig" \
  --certificate "$work_dir/kubernetes-src.tar.gz.cert" \
  --certificate-identity krel-staging@k8s-releng-prod.iam.gserviceaccount.com \
  --certificate-oidc-issuer https://accounts.google.com

tar -xzf "$work_dir/kubernetes-src.tar.gz" -C "$work_dir/source"
tar -xzf "$work_dir/go.tar.gz" -C "$work_dir"
cd "$work_dir/source"
"$work_dir/go/bin/go" mod edit \
  -require=golang.org/x/net@v0.62.0 \
  -require=golang.org/x/text@v0.41.0
env GOCACHE="$work_dir/cache/build" GOMODCACHE="$work_dir/cache/modules" \
  GOTOOLCHAIN=local GOWORK=off \
  "$work_dir/go/bin/go" mod tidy -compat=1.26

readonly ldflags='-s -w
  -X k8s.io/client-go/pkg/version.buildDate=2026-10-27T12:02:52Z
  -X k8s.io/component-base/version.buildDate=2026-10-27T12:02:52Z
  -X k8s.io/client-go/pkg/version.gitCommit=ae6fece6fea92ecfcccd13af7d5f2ea8cb9b33fe
  -X k8s.io/component-base/version.gitCommit=ae6fece6fea92ecfcccd13af7d5f2ea8cb9b33fe
  -X k8s.io/client-go/pkg/version.gitTreeState=archive
  -X k8s.io/component-base/version.gitTreeState=archive
  -X k8s.io/client-go/pkg/version.gitVersion=v1.35.10-cogniflow.1
  -X k8s.io/component-base/version.gitVersion=v1.35.10-cogniflow.1
  -X k8s.io/client-go/pkg/version.gitMajor=1
  -X k8s.io/component-base/version.gitMajor=1
  -X k8s.io/client-go/pkg/version.gitMinor=35
  -X k8s.io/component-base/version.gitMinor=35'
env CGO_ENABLED=0 GOCACHE="$work_dir/cache/build" GOMAXPROCS=2 \
  GOMODCACHE="$work_dir/cache/modules" GOTOOLCHAIN=local GOWORK=off \
  "$work_dir/go/bin/go" build -buildvcs=false -mod=mod -p=2 -trimpath \
  -tags=selinux,notest,grpcnotrace -ldflags="$ldflags" \
  -o "$work_dir/kubectl" ./cmd/kubectl
echo "$binary_sha256  $work_dir/kubectl" | sha256sum --check --strict -
install -m 0755 "$work_dir/kubectl" "$output_dir/bin/kubectl"
