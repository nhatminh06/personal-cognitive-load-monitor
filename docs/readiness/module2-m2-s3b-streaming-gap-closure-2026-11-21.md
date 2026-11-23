# M2-S3B — Independent streaming qualification gap closure (2026-11-21)

**Decision: PASS_STREAMING_INDEPENDENT.** Fresh Java/JUnit tests, six malformed behavioral cases, two behavioral sessions, and continuous resource evidence close the four gaps recorded in [M2-S3A](module2-m2-s3a-streaming-recovery-2026-11-21.md). The pass is limited to the local Kafka → Flink → Redis workflow with synthetic data, the exact qualified images below and the bounded resource configuration. It does not qualify Spark, full Module II, cloud, Kubernetes or production.

## A. Preflight and security evidence

Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. Existing edits to `Makefile`, `jobs/internal_job_runner.py` and two tests, plus untracked reports, test and fixture, were preserved. The M2-S3A manifest verified before this run. Host preflight: 12 CPUs, 15 GiB RAM, 6.9 GiB initially available, 12 GiB free swap and 142 GiB free repository disk. The isolated runtime started only after image ID and retained raw Trivy JSON checks.

| Service image, Linux/amd64 | Exact local ID | Retained scan SHA-256 | HIGH / CRITICAL |
| --- | --- | --- | --- |
| Kafka and topic init, `cogniflow-kafka:c43-patched` | `sha256:158594103c0e9a9986fd599043af25ed2a4a9a50f5925d4234a5b8dba6eb06a0` | `3044c5add00bf027baa0150b43da49657d7456598c8167b1ae9492431d64fd78` | 0 / 0 |
| Flink JobManager, TaskManager and submit, `cogniflow-flink:c42-patched` | `sha256:3147c3a836514a84acd7eb41568e33e408f0d49866c36d17f690926334b15ecb` | `ac6a391e2173c2dd0355b33d78166401b7059b5ae03f80944b5b5057f934ed04` | 0 / 0 |
| Redis, `redis:7.4.12-alpine3.22` | `sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe` | `5804fa07e41ccc911057a1c036c61dfa170135d8341d84e90614ece3201c493b` | 0 / 0 |

The JSON checksums matched and parsing found zero HIGH/CRITICAL entries. These are applicable retained exact-image scans, not new M2-S3B scans. No image, Spark artifact or dependency was rebuilt or upgraded. The dedicated `cogniflow-m2s3b-20261121` Compose graph contained only Kafka, topic init, Redis and the three Flink services. It used separate network and volumes, loopback host ports 49092/46379/48082 and synthetic credentials. Shared `cogniflow-module2` resources were not touched.

## B. Java/JUnit root cause and outcome

M2-S3A lacked a Maven executable on both the host and qualified Flink runtime image; there was no recorded Java test failure. The existing Flink Dockerfile pins Maven **3.9.11** in its builder. Downloaded that exact Apache binary into ignored task evidence and verified its SHA-512 against Apache's published hash (`bcfe4fe305c962ace56ac7b5fc7a08b87d5abd8b7e89027ab251069faebee516b0ded8961445d6d91ec1985dfe30f8153268843c89aa392733d1a3ec956c9978`). The Apache `.sha512` file contains a bare digest, so the first `sha512sum -c` format check failed; direct digest comparison then passed. Java was OpenJDK **21.0.13.0.3**; Maven compiled the unchanged POM with `--release 17` and its original Flink 1.20.5, Kafka connector 3.3.0-1.20, JUnit 5.11.4 and other declared versions.

Command in a task-owned source copy: `build/m2-s3b-2026-11-21/apache-maven-3.9.11/bin/mvn -B -ntp -f build/m2-s3b-2026-11-21/source/infra/module2/flink/pom.xml -Dmaven.repo.local=/home/pnmynh/Documents/personal-cognitive-load-monitor/build/m2-s3b-2026-11-21/m2 test`. Dependency resolution succeeded into the isolated Maven cache. Surefire 3.5.2 reported **6 tests, 0 failures, 0 errors, 0 skipped; BUILD SUCCESS**. The platform-encoding and missing SLF4J binding warnings were non-fatal. Raw log and Surefire XML/text are retained and checksummed. No Java source or POM changed.

## C. Malformed behavioral event results

Six fixed synthetic behavioral records exercised unsupported schema version, missing `window_id`, inconsistent window end, negative active seconds, an unknown `private_url`, and an invalid UUID. Every record had a synthetic private marker in an allowed source field; the unknown-field case also carried it in `private_url`. All six were independently consumed from `cogniflow.dead-letter.v1` with `reason=invalid_event`, exception type, raw byte count and the SHA-256 of the exact published record. The six distinct hashes mapped one-to-one to the fixture labels. Neither raw payload nor private marker appeared in the dead-letter records. None produced a behavioral feature or replaced either Redis key. The Flink job remained RUNNING with 7/7 tasks, and valid records published after the malformed cases were processed.

The fixture is retained as `build/m2-s3b-2026-11-21/behavioral-fixture.jsonl`, with a self-checking SHA-256 file and a task evidence manifest. Dead-letter metadata identifies invalid records by raw hash rather than trusting their possibly malformed event IDs.

## D. Second-session correctness results

Two distinct session IDs were interleaved on the real behavioral topic. Session A's latest valid window [00:05, 00:10) UTC produced active/idle **200/100 seconds**, keyboard/pointer **14/5**, source event UUID `00000000-0000-0000-0000-000000000066`; session B's [00:15, 00:20) produced **150/150**, **7/9**, UUID `00000000-0000-0000-0000-0000000000ca`. Independent literal fixture oracles also checked window ID, start/end, cutoff, source, switch count 2, null optional counts, schema version and distinct Redis keys. Each expected valid event appeared once in the consumed behavioral feature output; an exact replay of A's latest event produced no second output. An older, distinct A record was emitted while the source watermark was still below its event time; the Redis freshness Lua rejected its older cutoff. A retained its newer record and B remained unchanged.

For the same session IDs, the existing authenticated `/features/{session_id}` HTTP route returned 200 and the independently published **rolling** snapshot values 11 and 22. The API was exercised in-process through ASGI with an isolated Redis URL and synthetic key. The repository has no behavioral-feature HTTP read route; behavioral values were checked directly in Redis. This distinction prevents claiming an HTTP behavioral read contract that does not exist.

## E. Redis and dead-letter verification

Both behavioral Redis keys matched the independent oracles after all interleaved, duplicate and older inputs; their TTLs were positive and no more than 3600 seconds. The older A write did not affect B. The six invalid dead-letter records were consumed by a separate Kafka consumer, not inferred from producer acknowledgments. The older valid A record was **not** quarantined as late in this run because the watermark had not advanced sufficiently; its emission was observed and Redis still rejected it. M2-S3A's separate late-event evidence remains scoped to that earlier run. Output Kafka sinks are configured for **at-least-once** delivery. Logical deduplication and Redis freshness are not an exactly-once transport guarantee.

## F. Continuous resource measurements

A task-owned sampler ran `docker stats --no-stream` from before startup through the bounded test and recorded UTC timestamps. Its requested two-second pause yielded actual roughly **4.05–5.08 second** intervals because each Docker sample has overhead. The first 640 MiB JobManager configuration collected 68 timestamped samples over about 275 seconds; the 768 MiB candidate collected 23 samples over about 91 seconds. Sampled maxima are not labeled exact peaks. Kernel cgroup `memory.peak`, `memory.max` and `memory.events` were captured separately.

| Candidate service | Sampled max memory | Kernel peak memory | Cgroup limit | Headroom from kernel peak | Sampled max CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| Kafka | 484.4 MiB | 579.6 MiB | 768 MiB | 188.4 MiB | 105.94% |
| Flink JobManager | 616.3 MiB | 632.8 MiB | 768 MiB | 135.2 MiB | 204.63% |
| Flink TaskManager | 700.5 MiB | 736.5 MiB | 768 MiB | 31.5 MiB | 199.77% |
| Redis | 9.9 MiB | 23.7 MiB | 192 MiB | 168.3 MiB | 5.70% |

At 640 MiB, JobManager's cgroup peak reached its exact limit, with **3 `memory.events max`** hits and no OOM; sampled max was 513.2 MiB. The 768 MiB candidate had **zero `max`, OOM and OOM-kill events** across all four services; all restart counts were zero. JobManager's memory limit was therefore raised by the smallest tested increment that provided material headroom. TaskManager's 31.5 MiB headroom is narrow and limits this result to the tested bounded input. Kafka and Redis data usage were measured inside task-owned volumes; exact measurements are retained under `disk-*-768m.txt`. The candidate finished with five completed checkpoints, zero failed and zero restored; M2-S3B did not repeat failure injection. [M2-S3A](module2-m2-s3a-streaming-recovery-2026-11-21.md) independently records explicit checkpoint 13 restoration with the same Flink source and image. The changed JobManager limit does not alter its checkpoint logic, but recovery at the new limit was not freshly injected here.

## G. Regression results

| Check | Fresh result |
| --- | --- |
| Flink Java/JUnit in isolated source copy | 6 passed, 0 skipped |
| `make module2-independent-regression` | 29 passed |
| Focused online-feature, smoke-fixture and Compose/rehearsal Python tests | 20 passed, 1 Starlette deprecation warning |
| `make test` with task-owned uv cache and loopback access | 707 passed, 2 skipped, 5 warnings; 86.95% coverage, above 81% gate |
| `.venv/bin/ruff check src scripts jobs dags pipelines` | PASS |
| `.venv/bin/mypy jobs/internal_job_runner.py` | PASS |
| `docker compose -f infra/module2/docker-compose.yml config --quiet` | PASS, parse only |
| `git diff --check` | PASS |

The initial sandboxed `make test` failed because uv's default cache was read-only; a retry with a writable task cache then reached a loopback tracing test failure/hang and was interrupted. The same unchanged suite passed with loopback access available. Neither interrupted attempt is counted as a regression pass. Helm and Terraform checks were outside this Compose-only change.

## H. Source changes and cleanup

Only `infra/module2/docker-compose.yml` changed in production configuration: Flink JobManager `mem_limit` **640m → 768m**. This preserves the Java job, schemas, images, external APIs and security gates. The original 640 MiB cgroup limit hits demonstrated the need; a fresh 768 MiB isolated run demonstrated headroom and passed the behavioral checks. This report is the other new repository artifact. All disposable M2-S3B containers, network and volumes were removed; existing Module II containers and volumes remained. No Spark, Airflow, Trino/dbt, Kubernetes, cloud, registry, production or remote Git action occurred.

Raw redacted evidence remains in ignored `build/m2-s3b-2026-11-21/`: Maven binary/hash and isolated cache, JUnit reports, synthetic fixture and observed Kafka records, Redis snapshots, Flink jobs/checkpoints, cgroup counters, continuously sampled stats, logs and disk measurements. Credential literals were removed from retained Compose and probe source. `evidence.sha256` SHA-256 is `1fc7b286e412e6c7f345b0622419d73c346015ac256485259f113e5d6ec4b0ae`; all listed files verified. Reproduction requires injecting fresh synthetic credentials into the redacted Compose copy and passing them as `M2S3B_REDIS_PASSWORD` and `M2S3B_API_KEY`; do not use production secrets.

## I. Remaining limitations

The candidate is a bounded local test, not a load or soak result. TaskManager headroom was only 31.5 MiB at its kernel peak; larger traffic may require separate sizing and acceptance. M2-S3B did not requalify checkpoint recovery after the resource-only Compose change, test deduplication TTL expiration, or prove exactly-once Kafka output. The behavioral stream's older valid record was emitted before its watermark advanced; this run does not add a new late-event pass. The HTTP feature read endpoint serves rolling session features, not behavioral feature records. Security evidence is retained exact-image scan evidence, not a new vulnerability scan. Cloud and production controls remain unverified.

## J. Final decision

**PASS_STREAMING_INDEPENDENT** for the qualified local image IDs, unchanged Flink application source and bounded synthetic Kafka → Flink → Redis workflow with the 768 MiB JobManager configuration. The four M2-S3A gaps are closed at this scope. Spark remains **BLOCKED / DEFER_SPARK_ENFORCED**; full Module II **UNVERIFIED**; cloud/Kubernetes **NOT QUALIFIED**; production **NOT READY**.
