# Reproducible local demo

## Isolated PR rehearsal

Use the rehearsal override when existing development resources must remain
untouched. The bootstrap is dry-run by default; `--execute` creates only the
isolated configuration, fresh secret file and preflight evidence. It does not
start containers or imply a successful runtime rehearsal.

```bash
python scripts/module2_e2e_rehearsal.py
python scripts/module2_e2e_rehearsal.py --execute \
  --project cogniflow-rehearsal-YYYYMMDDa \
  --run-dir build/module2-rehearsal/REHEARSAL_ID
```

Use the generated `0600` `.env.secrets` with both
`infra/module2/docker-compose.yml` and
`infra/module2/docker-compose.rehearsal.yml`. Run these checkpoints in order:

1. ingestion + lake, then `scripts/module2_rehearsal_fixture.py`;
2. batch, then Spark twice; stop Spark;
3. analytics, query Trino, and run dbt twice; stop analytics;
4. ingestion + streaming, submit the Flink job, then run
   `scripts/module2_rehearsal_stream.py`; restart only its TaskManager and
   verify checkpoint restoration; stop streaming and ingestion;
5. lake + batch + analytics + orchestration, reserialize the DAG and run
   `airflow dags test cogniflow_bronze_to_gold YYYY-MM-DD`;
6. capture `docker stats --no-stream`, task states and hashes, then use Compose
   `stop` with the same project and profiles. Never use `down -v` for evidence
   you intend to preserve.

Spark and Flink must not overlap on the current 15 GiB host. Before batch,
verify the exact SEC-022 image ID and all Ivy JAR hashes. Every Docker command
must include the generated project name and both Compose files; a command that
falls back to `cogniflow-module2` is unsafe and must be aborted.

1. Start ingestion and lake profiles; submit an authenticated `/events` request.
2. Run the Bronze consumer and verify the stored JSONL checksum/readback.
3. Start batch, run `jobs/bronze_to_silver.py`, then query Silver through Trino.
4. Run `dbt build` twice and query `lakehouse.gold.gold_session_summary`.
5. Stop batch/analytics. Start ingestion/streaming and submit a new event.
6. Verify Flink `/jobs/overview`, Redis, `cogniflow.features.v1`, and `GET /features/{session_id}`.
7. Stop streaming. Start orchestration dependencies and run `airflow dags test cogniflow_bronze_to_gold YYYY-MM-DD`.
8. Finish with `make module2-stop`; use `make module2-ps` and `docker stats --no-stream` for evidence.

9. Show `benchmark-report.json`, `manifest.json` and partition checksums only if
   an explicitly authorized >100 GB run actually completed; otherwise show the
   small-fixture tests and state “not completed.”
10. Show cloud evidence only for deployments that were separately authorized
    and executed; otherwise show `cloud-deferred.md` and state “not completed.”

Suggested evidence filenames: `01-kafka-topics.txt`, `02-bronze-sha256.txt`,
`03-delta-history.json`, `04-trino-silver.txt`, `05-dbt-build.txt`,
`06-airflow-dag.txt`, `07-flink-job.json`, `08-redis-feature.json`,
`09-feature-api.json`, `10-benchmark-report.json`, and `11-ci-summary.txt`.

Exact component commands and credentials are in `.env.module2.example` and the topic/storage documents. Do not expose these development ports or credentials.
