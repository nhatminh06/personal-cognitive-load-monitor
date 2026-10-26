# Opt-in 100GB benchmark plan

No 100GB dataset was generated or processed locally. A later approved benchmark must run on an isolated, budget-capped environment.

1. Record image digests, commit SHA, schema version and generator seed. Set a hard generator `--max-bytes` ceiling of 100 GB plus one record and a storage free-space reserve of at least 20 GB.
2. Provision lifecycle-limited storage and compute with billing alerts, quotas and an automatic shutdown deadline. Never use production credentials or personal data.
3. Generate into partitioned objects, recording bytes, rows, SHA-256 manifests, wall time, CPU, peak RSS and storage growth. Resume only from the atomic state manifest.
4. Measure Kafka publish/consume throughput and retries; Bronze object counts/size; Spark input/output bytes, shuffle and duration; Delta rows/history; Trino/dbt duration; Flink lag/checkpoints/backpressure; Redis freshness.
5. Reconcile source, Bronze, Silver and Gold counts and duplicate/invalid/late-event totals. Save commands and raw metrics before deleting resources.
6. Stop compute immediately after measurement and verify lifecycle deletion. Report actual cloud cost separately from estimates.

The default generator remains capped at 100 MB. Large runs require an explicit count, `--max-bytes`, and adequate `--min-free-bytes`; there is no implicit “100GB mode.”
