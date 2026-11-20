# Module II: data platform

## Data flows

The batch path is Kafka → SeaweedFS Bronze → Spark/Delta Silver → Trino/dbt Gold.
The online path is Kafka → Flink event-time windows → Redis. Airflow orchestrates
the six-step Bronze-to-Gold DAG: source check, input validation, Spark transform,
Silver verification, dbt build/tests and Gold verification.

Events use versioned Pydantic contracts. Bronze writes immutable JSONL batches
with Kafka partition/offset provenance and SHA-256 metadata. Spark validates the
exact SEC-022 dependency bundle, reads Bronze through S3A and merges into Delta by
`event_id`. dbt builds six incremental Gold models and contract tests. Flink
deduplicates event IDs, applies bounded-out-of-order watermarks and writes only
fresh feature records to Redis.

## Local operation

Use `.env.module2.example` as the non-secret template. Compose profiles are
`ingestion`, `lake`, `batch`, `analytics`, `streaming`, `orchestration` and
`orchestration-dev`.
The bounded rehearsal entry point is `scripts/module2_e2e_rehearsal.py`; it creates
a unique Compose project and private secret file under ignored `build/` evidence.

## Verified scope and limits

- Kafka/Bronze, Spark/Delta replay, Trino/dbt replay and all six Airflow tasks
  passed in the isolated 2026-11-19 rehearsal. Gold reconciled 3 accepted rows;
  52,363 bytes measured all objects under the Gold storage prefix, including any
  stale or unrelated objects, rather than only the six current tables.
- The historical Flink zero-consumption attempts failed. After the Kafka topic
  initialization race was fixed, two fresh isolated streaming rehearsals passed:
  800 focus minutes, 410 distraction events and 10 unique events. Three duplicate
  publications caused no inflation. Redis rejected stale writes, the authenticated
  API returned HTTP 200, and invalid and late events were quarantined. Five
  checkpoints were observed in the earlier successful run; checkpoint 3 was
  explicitly restored and processing and API access continued after recovery.
  Earlier zero-valued Flink REST counters remain unexplained. The final local
  streaming-fix regression had 696 Python tests passed, 2 skipped, 87.00%
  coverage and six Flink Java tests passed.
- SeaweedFS supplies the S3-compatible API. It is not claimed as instructor
  acceptance for an explicit MinIO requirement.
- The maintained Spark image still has the documented **SEC-022 development-only
  exception**. It must not be deployed to Kubernetes, GKE or production.
- No >100 GB benchmark, four-cloud deployment, HA or cloud runtime is claimed.

The event schema is [session-event-v1.json](module2/schemas/session-event-v1.json).
The exact SEC-022 terms are retained in
[the exception record](security-audit/sec-022-development-exception-proposal.md).
