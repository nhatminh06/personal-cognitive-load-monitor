# C8.2 bulk ingestion and end-to-end reconciliation

**Verification date:** 2026-11-18. **Implementation status:** complete and
contract-tested. **Runtime status:** `NOT_RUN` for Kafka/SeaweedFS/Spark because
the fresh host gate had only 4,046,929,920 available bytes, below the mandatory
6 GiB. No service or cluster was changed.

## Executable flow

Generate the source with `generate_module2_benchmark.py`, then ingest it with:

```bash
uv run --extra module2 python scripts/module2_bulk_ingest.py \
  --dataset /isolated-volume/cogniflow-module2 \
  --checkpoint /isolated-volume/evidence/ingestion-checkpoint.json \
  --report /isolated-volume/evidence/ingestion-report.json \
  --batch-records 5000 --max-source-bytes 110000000000 \
  --min-free-bytes 20000000000 --execute --allow-over-100gb
```

Repeat with `--resume` after an interruption. The driver verifies the generator
manifest totals and sequence, rehashes each partition before reading it, validates
each event incrementally, bounds each in-memory batch to at most 10,000 records,
and records a checkpoint before and after broker acknowledgment. The Kafka
producer uses all-replica acknowledgments, idempotence, bounded queue polling and
a 30-second batch deadline. A checkpoint advances only after the deterministic
Bronze object is written, metadata-checked and independently read back with the
same byte length and SHA-256.

The checkpoint records manifest identity, partition and byte/row position,
Kafka state and acknowledged offsets, Bronze evidence chain, processing status,
attempt count and a bounded failure history. An interruption after Kafka
acknowledgment reconstructs the exact source batch and writes Bronze without
republishing. An interruption during publication retries stable event IDs;
downstream Delta still excludes duplicate event IDs. Corrupt partitions,
inconsistent manifests, changed checkpoints and partial evidence fail closed.

The Spark job now reads `session_events/` through Spark's distributed S3A JSON
reader instead of collecting all Bronze records into Python driver memory. It
records paginated object bytes, rows actually read, valid/rejected rows,
duplicates excluded, batch and total Silver rows, Delta physical bytes and
history. The existing MERGE-by-`event_id` and six-feature transformations are
unchanged. Set `SPARK_EVIDENCE_PATH` to persist its atomic JSON report.

After a successful dbt build, collect Gold evidence:

```bash
uv run python scripts/collect_module2_gold_evidence.py \
  --endpoint http://127.0.0.1:8081/v1/statement \
  --output /isolated-volume/evidence/gold-report.json
```

Finally, require all three actual stage reports:

```bash
uv run python scripts/reconcile_module2_benchmark.py \
  --ingestion-report /isolated-volume/evidence/ingestion-report.json \
  --spark-report /isolated-volume/evidence/spark-report.json \
  --gold-report /isolated-volume/evidence/gold-report.json \
  --output /isolated-volume/evidence/final-reconciliation.json
```

The final reconciler keeps source-file, Kafka-payload, Bronze-object, Spark-input,
Delta-physical and Gold-physical bytes as distinct units. It requires logical
source/Kafka/Bronze record equality, Spark valid+rejected accounting, explicit
duplicate exclusion and Silver/Gold snapshot equality. Missing or `NOT_RUN`
Spark/Gold evidence is a hard failure.

## Fresh validation

- bulk ingestion, source integrity, Kafka acknowledgments, verified Bronze,
  checkpoint interruption/restart, publication/storage failure, corrupt
  readback, inconsistent manifest, atomic checkpoint recovery and reconciliation:
  37 focused tests passed;
- broader Module II source suite: 87 passed;
- full Python regression: 642 passed, 5 skipped, 86.99% coverage (81% gate
  passed);
- Ruff passed; scoped MyPy passed for 17 files;
- both Compose configurations rendered without starting services;
- Spark source compiled, but the unqualified Spark image was not executed.

The fresh runtime preflight measured 4,046,929,920 bytes available RAM,
10,614,648,832 bytes swap used, 83,030,016 bytes free in `/tmp`, and
126,715,535,360 persistent bytes free. Kafka, SeaweedFS and initializer image
IDs matched their qualified ledger. The memory gate stopped the isolated fixture
before container creation, so actual local Kafka offsets, S3 objects and restart
evidence are `NOT_RUN`, not inferred from tests.

This implementation makes a future authorized >100 GB run executable, but does
not complete the rubric. It still needs a host meeting the documented resource
budget, real qualified-component execution, a normally qualified Spark image,
MinIO resolution and actual stage reports from more than 100,000,000,000
processed bytes. SeaweedFS remains development S3 evidence, not MinIO credit.
