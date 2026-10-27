# Reproducible local demo

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
