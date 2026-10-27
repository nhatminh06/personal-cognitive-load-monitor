# Reproducible isolated local demo

This procedure is only for a disposable rehearsal. It does not use the shared
development Compose project. The bootstrap is dry-run by default; `--execute`
creates the isolated configuration, a new secret file and preflight evidence.
It does not start containers or imply a successful runtime rehearsal.

Choose a new project and evidence directory. The execute command fails if the
directory or `.env.secrets` already exists.

```bash
python scripts/module2_e2e_rehearsal.py
python scripts/module2_e2e_rehearsal.py --execute \
  --project cogniflow-rehearsal-YYYYMMDDa \
  --run-dir build/module2-rehearsal/REHEARSAL_ID

rehearsal_compose=(
  docker compose
  --env-file build/module2-rehearsal/REHEARSAL_ID/.env.secrets
  -p cogniflow-rehearsal-YYYYMMDDa
  -f infra/module2/docker-compose.yml
  -f infra/module2/docker-compose.rehearsal.yml
)

"${rehearsal_compose[@]}" --profile ingestion --profile lake up -d
python scripts/module2_rehearsal_fixture.py

"${rehearsal_compose[@]}" --profile lake --profile batch up -d
# Run jobs/bronze_to_silver.py twice through the authenticated Spark runner.
"${rehearsal_compose[@]}" --profile batch stop

"${rehearsal_compose[@]}" --profile lake --profile analytics up -d
# Query Silver through Trino, run dbt build twice, and capture Gold counts.
"${rehearsal_compose[@]}" --profile analytics stop

"${rehearsal_compose[@]}" --profile ingestion --profile streaming up -d
# Submit Flink, then exercise windows, deduplication and Redis freshness.
python scripts/module2_rehearsal_stream.py
"${rehearsal_compose[@]}" restart flink-taskmanager
# Verify the job returns to RUNNING and reports a restored checkpoint.
"${rehearsal_compose[@]}" --profile ingestion --profile streaming stop

"${rehearsal_compose[@]}" --profile lake --profile batch \
  --profile analytics --profile orchestration --profile orchestration-dev up -d
# Reserialize the DAG and run its six tasks with airflow dags test.
"${rehearsal_compose[@]}" --profile lake --profile batch \
  --profile analytics --profile orchestration --profile orchestration-dev stop

"${rehearsal_compose[@]}" --profile '*' ps -a
"${rehearsal_compose[@]}" ps -q | xargs --no-run-if-empty docker stats --no-stream
"${rehearsal_compose[@]}" --profile '*' stop
```

Every rehearsal Compose operation above expands the same command containing
the disposable project name, secret file and both Compose files. Do not replace
it with a Make target or omit `-p`; either change can select shared resources.
Never use `down -v` for evidence that must be preserved.

Spark and Flink must not overlap on the current 15 GiB host. Before batch,
verify the exact SEC-022 image ID and every Ivy JAR hash. Use only small
synthetic fixtures unless the larger benchmark has separate authorization.

Show `benchmark-report.json`, `manifest.json` and partition checksums only if
an explicitly authorized >100 GB run actually completed; otherwise show the
small-fixture tests and state “not completed.” Show cloud evidence only for a
separately authorized deployment; otherwise show `cloud-deferred.md` and state
“not completed.”

Suggested evidence filenames are `01-kafka-topics.txt`,
`02-bronze-sha256.txt`, `03-delta-history.json`, `04-trino-silver.txt`,
`05-dbt-build.txt`, `06-airflow-dag.txt`, `07-flink-job.json`,
`08-redis-feature.json`, `09-feature-api.json`, `10-benchmark-report.json` and
`11-ci-summary.txt`. Never include `.env.secrets` in an artifact or log.
