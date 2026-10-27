#!/usr/bin/env bash
set -euo pipefail

matrix=${1:?usage: negative-tests.sh QUALIFIED_MATRIX VALID_RUNTIME_SNAPSHOT}
snapshot=${2:?usage: negative-tests.sh QUALIFIED_MATRIX VALID_RUNTIME_SNAPSHOT}
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

for mutation in version image crd autoscaling route; do
  case "$mutation" in
    version) jq '.knative_serving="0.0.0"' "$snapshot" >"$workdir/$mutation.json" ;;
    image) jq '.controllers["knative-serving/controller"].image="invalid:latest"' "$snapshot" >"$workdir/$mutation.json" ;;
    crd) jq 'del(.crds[0])' "$snapshot" >"$workdir/$mutation.json" ;;
    autoscaling) jq '.autoscaler["enable-scale-to-zero"]="false"' "$snapshot" >"$workdir/$mutation.json" ;;
    route) jq '.routes.predict="http://incorrect/predict"' "$snapshot" >"$workdir/$mutation.json" ;;
  esac
  if python scripts/module1_compatibility.py --matrix "$matrix" --require-qualified --snapshot "$workdir/$mutation.json"; then
    echo "negative test unexpectedly passed: $mutation" >&2
    exit 1
  fi
done
