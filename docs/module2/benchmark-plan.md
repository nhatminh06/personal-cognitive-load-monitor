# Opt-in 100GB benchmark plan

No 100GB dataset was generated or processed locally. A later approved benchmark must run on an isolated, budget-capped environment. `scripts/generate_module2_benchmark.py` implements the source-generation portion with exact-byte partitioning, a single authoritative manifest, crash recovery, per-partition SHA-256/row/event-ID evidence, a machine-readable report, human summary, disk reserve and peak-RSS evidence.

## Crash-consistent commit protocol

Only `manifest.json` records committed progress; there is no independent
checkpoint counter to drift. A generator takes a non-blocking exclusive lock
on the output directory, writes and synchronizes a uniquely created temporary
partition, publishes it with a no-overwrite hard link, and synchronizes the
directory. It then independently re-reads the deterministic partition,
recomputes its byte count, rows and SHA-256 evidence, writes a synchronized
temporary manifest, atomically replaces the manifest, and synchronizes the
directory again.

`--resume` never trusts the manifest counters. It verifies every committed
partition from index zero, removes incomplete partition temporaries, adopts
only the one exact deterministic next partition left by a crash before the
manifest commit, and rewrites reconciled counters. Missing, modified,
out-of-sequence, extra or wrong-sized partitions fail closed for inspection.
An interrupted manifest temporary is discarded when the prior manifest is
present; a synchronized valid initial manifest can be promoted if no committed
manifest exists. A completed partition is never overwritten.

1. Record image digests, commit SHA, schema version and generator seed. Set a hard generator `--max-bytes` ceiling of 100 GB plus one record and a storage free-space reserve of at least 20 GB.
2. Provision lifecycle-limited storage and compute with billing alerts, quotas and an automatic shutdown deadline. Never use production credentials or personal data.
3. Generate into partitioned objects, recording bytes, rows, event-ID evidence, SHA-256 manifests, wall time, CPU, peak RSS and storage growth. Resume only through verified reconciliation with the authoritative manifest.
4. Measure Kafka publish/consume throughput and retries; Bronze object counts/size; Spark input/output bytes, shuffle and duration; Delta rows/history; Trino/dbt duration; Flink lag/checkpoints/backpressure; Redis freshness.
5. Reconcile source, Bronze, Silver and Gold counts and duplicate/invalid/late-event totals. Save commands and raw metrics before deleting resources.
6. Stop compute immediately after measurement and verify lifecycle deletion. Report actual cloud cost separately from estimates.

The legacy event generator remains capped at 100 MB. The benchmark generator
requires both `--execute` and, above 100,000,000,000 bytes,
`--allow-over-100gb`. A qualifying run must target at least
`100000000001` actual bytes and set an independently reviewed maximum ceiling:

```bash
uv run python scripts/generate_module2_benchmark.py \
  --output /isolated-volume/cogniflow-module2 \
  --target-bytes 100000000001 \
  --max-bytes 110000000000 \
  --partition-bytes 128000000 \
  --min-free-bytes 20000000000 \
  --seed 42 --execute --allow-over-100gb
```

Do not run that command on a laptop or shared volume. Generation alone still
does not satisfy the rubric: the approved run must also process and reconcile
the recorded partitions through Bronze, Spark/Delta, Trino/dbt and the selected
Kafka/Flink subset.
