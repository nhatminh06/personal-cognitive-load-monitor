#!/usr/bin/env bash
set -euo pipefail

readonly output_dir="${1:?usage: $0 OUTPUT_DIRECTORY}"
readonly package="libbrotli1_1.1.0-2ubuntu0.1_amd64.deb"
readonly url="https://archive.ubuntu.com/ubuntu/pool/main/b/brotli/${package}"
readonly sha256="70b188a86d81f30d7510aab30e25d638ed5037dded6691af1533952b71ac61de"

mkdir -p "$output_dir"
curl --fail --location --proto '=https' --tlsv1.2 "$url" --output "$output_dir/$package"
echo "$sha256  $output_dir/$package" | sha256sum --check --strict -
