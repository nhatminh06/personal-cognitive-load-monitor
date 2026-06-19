#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://127.0.0.1:8000/health
curl -fsS -X POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"focus_minutes":120,"distraction_minutes":30,"tasks_due":3,"hours_to_deadline":24}'
echo
