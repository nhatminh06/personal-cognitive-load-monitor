# Evidence index

Evidence is scoped by date, revision and environment. Historical local Kubernetes
results are never relabeled as cloud results. Machine-readable assessments remain
under `docs/course-completion/*-evidence/`; schemas, checksums and candidate JSON
packets remain tracked.

| Area | Evidence | Status / limit |
|---|---|---|
| Python regression | 2026-11-19: 700 passed, 2 skipped; 87.00% coverage against an 81% gate; six Flink Java tests passed; merged main CI succeeded | Local host and GitHub CI; earlier 696-test streaming-fix run retained in Module II |
| Module I | Isolated qualification and final-acceptance records; compatibility and upstream-source JSON; qualification checksum | Preserved course evidence; no new cloud claim |
| Module II batch | 2026-11-19 isolated rehearsal: Kafka/Bronze, two Spark/Delta runs, two dbt builds, six Airflow tasks; 3 Gold rows / 52,363 bytes under the entire Gold storage prefix | PASS locally; prefix bytes are not current-table bytes |
| Module II streaming | Two fresh isolated rehearsals after Kafka topic-init fix: 800 focus, 410 distraction, 10 unique events; three duplicates did not inflate totals; stale Redis writes rejected; authenticated API 200; invalid/late quarantine; five checkpoints observed earlier and checkpoint 3 restored with processing continuing | PASS locally; earlier zero-consumption attempts are historical and zero-valued REST counters remain unexplained |
| KFP | 2026-10-26 positive `cee7540f-9c9e-4078-a9d7-c61c4c4bd9fc`; negative `5143c5ae-9c98-4c4d-9f21-f5647ec63cf9` | Historical isolated kind runtime |
| Knative Eventing | 2026-10-26 event `33fb0ed9-4b13-41f3-9da5-cdc30b444a31`; replay, restart, retry and DLQ recorded | Historical isolated runtime |
| Anomaly detection | 2026-10-26/27 runtime plus current recovery/concurrency regression tests | Exact hardened image not freshly redeployed |
| MLflow GCS image | Local index `sha256:a9741a4d3248444027c0f605114024e2294e25504cde7b5def31c18694f445f5`; runtime `sha256:9d92089f477271463d0753122c58d3cd2a8a7426f18a6e4c58b8d69e0aba8f05`; 0 HIGH/CRITICAL | Local-only; unpublished |
| Deployment runner | Local index `sha256:fea8be5e98ba4defff5f8d23059c9d31103f7014b4e33b42c1aa1dcb0498d44a`; runtime `sha256:3aab5b8fe68d83df3608c6cb1f7b3c1b02798643c068345344a56b8816b2b182`; 0 HIGH/CRITICAL | Local-only; unpublished |
| GKE/GCS | Terraform/Helm/static validation only | NOT RUN; authorization required |

The original weighted rubric is [course-rubric-2026.md](course-rubric-2026.md),
the original engineering checklist is [requirement-matrix.md](requirement-matrix.md),
and required handoff items remain in [submission_checklist.md](submission_checklist.md).
Candidate review packets `synthetic-candidate-20261117.json` and
`c22-candidate.json`, the predeclared C22 evaluation protocol and the model
candidate owner-review record are deliberately retained.
