#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 2 ]] || { echo "usage: $0 PLAN.json OUTPUT_DIR" >&2; exit 2; }
readonly plan=$1
readonly output_dir=$2
readonly preflight="$output_dir/c11-preflight.json"

mkdir -p -- "$output_dir"
set +e
.venv/bin/python scripts/c11_runtime_preflight.py --plan "$plan" --output "$preflight"
readonly preflight_status=$?
set -e
if [[ $preflight_status -ne 0 && $preflight_status -ne 3 ]]; then
  exit "$preflight_status"
fi

.venv/bin/python scripts/final_acceptance.py offline \
  --output-dir "$output_dir" --additional-evidence "$preflight"
.venv/bin/python scripts/validate_final_acceptance.py \
  "$output_dir/acceptance-report.json"

if [[ $preflight_status -eq 3 ]]; then
  echo "BLOCKED: C11 runtime gates did not pass" >&2
  exit 3
fi
