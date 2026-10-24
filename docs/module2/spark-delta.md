# Spark and Delta Silver

Spark 3.5.5 runs locally with one worker thread and a 1 GiB driver heap. Delta Lake 3.3.2 is selected by `delta-spark`; Hadoop AWS 3.3.4 matches the Spark distribution and supplies S3A access to MinIO.

`jobs/bronze_to_silver.py` validates every Bronze envelope, normalizes timestamps to UTC, deduplicates by `event_id`, computes the two ratios with the same zero-total semantics as Module I, partitions by event date, and merges into a real Delta table. Invalid records are counted for quarantine; a later production deployment should persist the rejection details in a separately access-controlled bucket.

Silver columns retain source and Kafka provenance plus the exact six model inputs. Checked-in parity vectors are evaluated by Module I tests and will be reused by Flink tests. The job prints row/rejection counts and Delta history. A successful rerun must keep the same event count while adding a Delta MERGE history entry.
