# Module II C4.3 Kafka remediation

Recorded 2026-11-17. This qualification covers only Kafka and its topic
initializer. It does not qualify Trino, Airflow, Spark, or the full rehearsal.

## Immutable inputs and security result

The previous `apache/kafka:3.9.2` image remains available for rollback as local
ID `sha256:05b4616e0702ef2729327705d54ad6b50ea70b271c4b730fabd2320789fb7b02`.
Trivy found 67 HIGH and 7 CRITICAL occurrences in it. That inventory included
CISA KEV `CVE-2026-111497` in `brotli-libs` 1.2.0-r0 (fixed in 1.2.1-r0), plus
fixable Kafka-runtime findings in Netty, Jackson, ZooKeeper, LZ4, Snappy,
Jetty, and JLine. No finding was ignored or downgraded.

The replacement is built by `infra/module2/kafka/Dockerfile` from official
`apache/kafka:4.4.0` pinned at
`sha256:833b867a9585a141da455dc2b57431c65cbccb27f11c91f694444cca9f777e0f`.
The build pins patched Alpine packages (`alpine-release` 3.24.4-r0,
`apk-tools`/`libapk` 3.0.9-r0, `brotli-libs` 1.2.1-r0, `ca-certificates`
and its bundle 20261020-r0, `libexpat` 2.10.0-r0, `musl`/`musl-utils`
1.2.6-r3, `tzdata` 2026f-r0, and `zlib` 1.4-r0). It also replaces
`lz4-java` 1.11.2 with 1.11.4 and `snappy-java` 1.1.10.7 with 1.1.10.9.
Maven downloads are checksum-pinned.
The resulting local image is `cogniflow-kafka:c43-patched` at
`sha256:a90beec03332d23649e3728e53ee13049fcf76564cabdc11ac940baaa0fc0d53`.

Trivy 0.76.2 scanned that exact ID with the vulnerability DB updated
2026-11-17 19:04 UTC and Java DB updated 2026-11-17 00:59 UTC. The complete
scan reported **0 HIGH and 0 CRITICAL**, no errors, and no unsupported-OS
warning. The raw JSON is retained outside Git at
`~/cogniflow-resource-backups/c41-image-scans/kafka-c43-pinned.json`; its
SHA-256 is `4ec3bf8458b5191712460e021bd99985646ae77523f4a24c6857a7359e645a4b`.

## Isolated compatibility evidence

The candidate ran alone on loopback port 39092 with a dedicated network and
volume, 1 CPU, and a 768 MiB memory limit. All seven existing topic names were
created with three partitions and replication factor one. The repository's
idempotent producer received `acks=all` for a valid and deliberately invalid
schema-v1 event at partition 2 offsets 0 and 1. A consumer read both records,
accepted the valid schema, rejected the negative `focus_minutes` fixture, and
committed offset 2 with zero lag.

After a broker restart, the topic identity and committed offset remained, and
a new consumer read both records again at offsets 0 and 1. This exposed and
corrected a configuration defect: Kafka 4.4 otherwise defaults outside the
mounted volume, so Compose now sets `KAFKA_LOG_DIRS=/var/lib/kafka/data`.

Peak observed broker memory for the exact final image was 382 MiB. The persistent directory had
1,509,989,196 apparent bytes after restart (mostly sparse/preallocated Kafka
files) and 675,840 allocated bytes as measured inside the container. The final
image is 719,385,246 bytes. Available RAM was 6,887,972,864 bytes at preflight,
6,460,661,760 bytes after the final restart, and 6,815,580,160 bytes after
cleanup. Memory pressure after the final restart was 0.02 for both `some` and
`full` avg10; the broker stayed within its limit. The test container, network,
volume, and fixtures were removed; only the two pre-existing kind control
planes remained running.

## Status

Kafka and its topic initializer are qualified for the bounded local rehearsal
only when the preflight observes the exact local image ID above. Rebuilds are
not presumed identical and must be rescanned. Trino, Airflow, and Spark remain
independent image-security blockers, so C4 cannot yet execute.

Focused Kafka/rehearsal tests passed 23/23. The full Python regression suite
passed 625 tests with 2 skipped and 87.20% coverage (81% required). Ruff,
scoped MyPy, Compose ingestion-profile validation, and `git diff --check`
passed. A final fail-closed rehearsal dry-run started no services and stopped
at the 6 GiB available-memory gate; therefore it did not reach the remaining
Trino, Airflow, and Spark image checks in that invocation.
