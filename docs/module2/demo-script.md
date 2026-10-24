# Reproducible local demo

1. Start ingestion and lake profiles; submit an authenticated `/events` request.
2. Run the Bronze consumer and verify the stored JSONL checksum/readback.
3. Start batch, run `jobs/bronze_to_silver.py`, then query Silver through Trino.
4. Run `dbt build` twice and query `lakehouse.gold.gold_session_summary`.
5. Stop batch/analytics. Start ingestion/streaming and submit a new event.
6. Verify Flink `/jobs/overview`, Redis, `cogniflow.features.v1`, and `GET /features/{session_id}`.
7. Stop streaming. Start orchestration dependencies and run `airflow dags test cogniflow_bronze_to_gold YYYY-MM-DD`.
8. Finish with `make module2-stop`; use `make module2-ps` and `docker stats --no-stream` for evidence.

Exact component commands and credentials are in `.env.module2.example` and the topic/storage documents. Do not expose these development ports or credentials.
