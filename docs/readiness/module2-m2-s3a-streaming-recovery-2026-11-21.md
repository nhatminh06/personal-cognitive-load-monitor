# M2-S3A — Independent Kafka → Flink → Redis recovery (2026-11-21)

**Decision: PARTIAL.** The isolated real streaming job, deterministic session window oracle, explicit checkpoint restoration, post-recovery processing, behavioral API path, Redis freshness, and scoped Python checks passed. The full requested qualification is withheld because the Java/JUnit suite could not run in this environment, behavioral invalid-payload and multi-session runtime coverage was incomplete, and resource sampling did not establish a peak envelope. Spark remains BLOCKED; full Module II remains UNVERIFIED.

## A. Preflight and image security

Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`; existing dirty files and untracked reports/fixture were preserved. Reviewed [CF-R1](cogniflow-cross-module-readiness-2026-11-21.md), [streaming checkpoint](../security-audit/module2-local-checkpoint-2026-11-21.md), Compose, the Flink job and tests, online API adapter, and existing smoke harness. Host: 12 CPUs, 15 GiB RAM, about 3.9 GiB initially available, 9.2 GiB free swap, 142 GiB free repository disk. No fixed minimum was specified for this milestone; available memory was monitored and stayed about 3.6–4.9 GiB in spot checks.

| Required image | Exact local image ID | Retained Trivy JSON SHA-256 | HIGH / CRITICAL |
| --- | --- | --- | --- |
| `cogniflow-kafka:c43-patched` (broker and init) | `sha256:158594103c0e9a9986fd599043af25ed2a4a9a50f5925d4234a5b8dba6eb06a0` | `3044c5add00bf027baa0150b43da49657d7456598c8167b1ae9492431d64fd78` | 0 / 0 |
| `cogniflow-flink:c42-patched` (JM, TM, submit) | `sha256:3147c3a836514a84acd7eb41568e33e408f0d49866c36d17f690926334b15ecb` | `ac6a391e2173c2dd0355b33d78166401b7059b5ae03f80944b5b5057f934ed04` | 0 / 0 |
| `redis:7.4.12-alpine3.22` | `sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe` | `5804fa07e41ccc911057a1c036c61dfa170135d8341d84e90614ece3201c493b` | 0 / 0 |

All images were local Linux/amd64. The exact IDs matched retained reports and raw scan JSON; raw JSON was parsed and contained zero HIGH/CRITICAL entries. These are retained security results, not fresh M2-S3A scans. No image was built or scanned.

## B. Isolation and resource budget

A dedicated `cogniflow-m2s3a-20261121` Compose project used its own network and Kafka/Redis volumes. The resolved graph contained only Kafka, topic init, Redis, Flink JobManager, TaskManager and submit. Host ports 39092/36379/38082 were loopback bound; the existing `cogniflow-module2` project and all its containers/volumes were untouched. A synthetic Redis credential was used and redacted from retained Compose evidence. No Spark, Airflow, Trino/dbt, cloud or Kubernetes component was started.

The first disposable attempt failed because a newly mounted checkpoint volume was not writable by Flink. It was removed. A second submission failed with `WRONGPASS` because the isolated TaskManager lacked the new synthetic Redis password; the task-owned configuration was corrected and a new job submitted. These failed job IDs are retained as troubleshooting evidence, not qualification passes. No production Compose or source file was changed.

## C. Deterministic input and oracle

Ignored raw fixture: `build/m2-s3a-2026-11-21/fixture.jsonl`; SHA-256 is in `fixture.sha256` and the evidence manifest. All session timestamps are fixed at 2026-11-21 00:00–00:40 UTC. Nine initial records cover two sessions, one duplicate event ID, a valid out-of-order event, a zero-total session, an invalid negative focus value with a synthetic private marker, a too-late event and watermark advancement. The independent target for session A's rolling [00:00, 00:05) window is focus 60, distraction 30, count 3, focus ratio 2/3, latest tasks due 4 and timestamp 00:03 UTC. Session B's zero-total ratios are 0. The later post-recovery [00:20, 00:25) target is focus 5, distraction 5, count 2 and ratio 0.5. Events at 00:20 and 00:40 advance watermarks; event-time assertions did not rely on sleep duration.

## D. Kafka ingestion results

Topic initializer exited 0 and created all seven configured topics. Session input offset high watermark moved from 9 before failure injection to 12 after replay/new events, in the task-owned broker partition 1. Feature output increased from 15 to 28 records across partitions; dead-letter output from 2 to 3. Exact partition offset snapshots are retained. Source offsets progressed; no production topic was used.

## E. Flink window and deduplication results

The successful job ID was `d49f36b2893a019257a7765132206466`; it reached RUNNING with 7/7 running tasks. The initial [00:00, 00:05) rolling record matched the six numerical oracle fields above, schema `1.0`, window bounds and `flink:kafka:cogniflow.session-events.v1` provenance. The session B Redis record retained 0/0 ratios. After recovery, the [00:20, 00:25) record matched 5/5, count 2 and ratio 0.5. A replayed pre-checkpoint event ID did not appear in the post-recovery dead-letter output or inflate that window. The 24-hour deduplication TTL is defined in source; this run was shorter and did not test expiration. Kafka sinks are **at-least-once**, so logical idempotence does not prove exactly-once delivery.

## F. Dead-letter and invalid-event results

The dead-letter stream independently yielded `invalid_event` and `event_time_behind_allowed_lateness`. The invalid record reported error type, raw size and SHA-256 without copying the synthetic private field or raw payload. The late event preserved event identity and time. Behavioral late-event quarantine passed in the existing real smoke harness. A separate malformed behavioral payload was not injected into this fresh runtime, so that specific runtime path remains unverified.

## G. Controlled checkpoint recovery

Before interruption the successful job had 11 completed checkpoints, 0 failed, 0 restored; latest completed ID was 11. Kafka offsets and Redis snapshots were retained. Only `cogniflow-m2s3a-20261121-flink-taskmanager-1` received a fast Docker restart. Flink recorded restored checkpoint **13** at restore timestamp `1795301590938`; the count changed to 2 restored, 13 completed and 1 failed immediately afterward. All 7 tasks returned to RUNNING and the job remained RUNNING. Final checkpoint counts were 22 completed, 1 failed, 2 restored. This explicitly demonstrates restored state, not merely a fresh job start. The replay/new-event oracle passed afterward. Recovery duration was not measured precisely enough to assert a bounded latency target.

## H. Redis freshness and online-feature results

The rolling Lua script accepted a newer value, rejected an older timestamp without replacing the stored value, and **accepted an equal timestamp**, replacing the prior value. The behavioral Lua script accepted a newer value, rejected an older value and **rejected equal cutoff timestamps**. Both test keys reported TTL 3600 seconds. Different session keys remained distinct. The API-backed behavioral smoke produced a record whose fields matched the independent Python projection in both Kafka and Redis; duplicate replay left Redis unchanged and an older window was quarantined. Rolling Redis stores the last emitted valid sliding window for a feature timestamp; multiple overlapping windows may share that timestamp, so Redis is not a durable history of every window. A separate persistent API server was not started; the harness used the approved in-process ASGI app.

## I. Resource and reliability results

A spot sample showed Kafka 208 MiB/768 MiB, JobManager 483.5 MiB/640 MiB, TaskManager 669.9 MiB/768 MiB, Redis 8.3 MiB/192 MiB. The sampled TaskManager was close to its limit; no OOM was reported and all Docker restart counters were 0 (the explicit Docker restart is separate). Kafka data was 732 KiB and Redis data 24 KiB at measurement. CPU spot readings were Kafka 38.47%, JobManager 1.17%, TaskManager 3.32%, Redis 0.60%; startup samples reached higher CPU but no continuous peak trace was collected. Available host RAM was about 3.9 GiB after the run. Resource safety passed for this bounded sample; sustained peak/resource-envelope acceptance remains unverified.

## J. Regression checks

- Existing offline independent target: **29 passed**.
- Focused online-feature, Flink smoke fixture and Module II rehearsal Python tests: **20 passed**, one Starlette deprecation warning.
- Ruff on `src scripts jobs dags pipelines`: PASS.
- Scoped MyPy on `jobs/internal_job_runner.py`: PASS.
- Isolated Compose config validation: PASS.
- `git diff --check`: PASS.
- Focused Java/JUnit: **NOT RUN**; Maven and a Maven wrapper were absent from the host and qualified Flink image. Historical Java results were not promoted to a fresh pass.

No production source changed, so a full Python suite, Helm lint and Terraform validation were not applicable to this scope.

## K. Code changes and cleanup

No tracked code, Compose file, security policy or dependency was changed. This report is the sole new tracked-path artifact. Test-owned containers, network and all three task-owned volumes (including the failed first checkpoint volume) were removed. Existing `cogniflow-module2` containers remained running. Raw fixture, source probes, redacted Compose, checkpoint/job JSON, offset snapshots, Redis snapshots, logs and checksums remain ignored under `build/m2-s3a-2026-11-21/`. `evidence.sha256` verified every listed file after credential redaction. The synthetic SQLite behavioral fixture is retained locally and is not included in the manifest because it was not needed for the reproducible oracle.

## L. Remaining limitations

Java tests, behavioral malformed-input runtime coverage, a second behavioral session, and continuous peak resource measurements remain open. Recovery duration and deduplication TTL expiry were not measured. The first setup and credential failures show the isolated harness requires writable checkpoint storage and consistent test credentials; the successful run used Flink's default checkpoint storage with the JobManager kept alive. It does not prove recovery from JobManager loss or durable external checkpoint storage. Scans are exact-image retained evidence, not fresh scans. No genuine Spark, full Module II, cloud or production qualification follows.

## M. Final qualification decision

**PARTIAL.** Real local streaming and checkpoint restoration passed against qualified image identities, with material evidence gaps listed above. Do not label the entire independent streaming milestone PASS until the missing Java, behavioral and resource gates are closed in a separate bounded run. Spark remains **BLOCKED / DEFER_SPARK_ENFORCED**; full Module II remains **UNVERIFIED**; cloud/Kubernetes **NOT QUALIFIED**; production **NOT READY**.
