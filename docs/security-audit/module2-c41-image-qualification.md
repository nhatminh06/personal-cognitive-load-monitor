# C4.1 Module II local image qualification — 2026-11-17

**Decision: FAIL.** No Module II rehearsal service was started. The exact local
images used by the bounded Compose profiles all have HIGH or CRITICAL findings
under the existing zero-HIGH/zero-CRITICAL deployment gate. SEC-022 remains an
accepted risk for its exact Spark image in isolated local development only;
this scan does not expand that exception or approve the new finding inventory.

The clean `main` tree was `f2bc12010a2874af9ff5466a227b1ef335cf1474`.
Trivy **0.76.2** scanned verified local Docker image IDs with `--image-src docker`,
`--scanners vuln`, `--severity HIGH,CRITICAL`, `--offline-scan`, and freshly
downloaded official vulnerability and Java databases. The vulnerability DB
was updated **2026-11-17 19:04:24 UTC** and the Java DB **2026-11-17 00:59:10
UTC**. Both downloaded successfully on 2026-11-17. All nine JSON scans exited
successfully and detected OS and language packages. Raw JSON is retained in a
private, persistent-disk scan directory outside Git. Counts are occurrences,
not unique CVEs. A local image ID is immutable for this scan; a Docker tag or
locally displayed RepoDigest is not proof of a remote registry manifest.
The nine raw JSON artifacts total 9,886,978 bytes. Their `SHA256SUMS` manifest
has SHA-256 `dd9c384b90246e99ea84bf3b6ef5ae9d2a56b94854e6d59d7331a42c5b16e540`.

| Compose services | Profile | Image and exact local ID (`sha256:`) | Provenance | HIGH | CRITICAL | Rehearsal need |
|---|---|---|---|---:|---:|---|
| `kafka`, `kafka-init` | ingestion | `apache/kafka:3.9.2` `05b4616e0702ef2729327705d54ad6b50ea70b271c4b730fabd2320789fb7b02` | Apache upstream image | 67 | 7 | Required |
| `seaweedfs`, `minio` (S3 gateway; not MinIO) | lake | `cogniflow-seaweedfs:4.50` `89fa460d0484b69f16304071fc0415cf5f18be2208814a4360a309cb5c654375` | `infra/module2/seaweedfs/Dockerfile`, upstream SeaweedFS 4.50 source | 2 | 0 | Required |
| `minio-init` (bucket initializer) | lake | `cogniflow-minio-init:module2` `52463a84ad84178f1614262fdf6c7931c430cdb0a7570160e0b77e150e360bbb` | `infra/module2/minio-init/Dockerfile`, Python 3.11 slim | 50 | 0 | Required |
| `spark` | batch | `cogniflow-spark:3.5.5-delta-3.3.2` `d55eac37429cb0d94208d79fcae0f1002662b1d9700eb1b4a522bbe6cf2bb0e8` | `infra/module2/spark/Dockerfile`, Apache Spark 3.5.5 base | 152 | 5 | Required; SEC-022 local-only |
| `trino` | analytics | `trinodb/trino:478` `177bda76e5e6caf235de4502e10020a029d06dd2625709fbf5adf264b6295a1d` | Trino upstream image | 119 | 8 | Required |
| `dbt`, `dbt-runner` | analytics, orchestration | `cogniflow-dbt-trino:1.11.14` `98946381d5eddc3417ed54a0a9c7e78134415af193c0e8dd5f80e6754a7cf475` | `infra/module2/dbt/Dockerfile`, Python 3.11 slim | 50 | 0 | Required |
| `flink-jobmanager`, `flink-taskmanager`, `flink-submit` | streaming | `cogniflow-flink:1.20.5` `bafb75f18fb2653bea6a1c819a7e5600c141ff3287b8d8145393e985eff3046a` | `infra/module2/flink/Dockerfile`, Maven builder and Flink 1.20.5 runtime | 4 | 0 | Required |
| `airflow` | orchestration-dev | `cogniflow-airflow:3.3.2` `6be8cf0965c00f7a4c5df3eb26b729a0145b8ca504f1b680a276bd6bd8cf9b16` | `infra/module2/airflow/Dockerfile`, Apache Airflow 3.3.2 slim | 248 | 5 | Required for Airflow stage |
| `redis` | streaming | `redis:7.4.2-alpine` `02419de7eddf55aa5bcf49efb74e88fa8d931b4d77c07eff8a6b2144472b6952` | Redis upstream image | 78 | 6 | Required |

The main FastAPI application runs on the host during the documented small
rehearsal; no API container is a service in these Compose profiles. A project
API image therefore was not scanned or counted as a required Compose image.
The dormant `infra/module2/minio/Dockerfile` and `minio-data` volume are not
part of the SeaweedFS rehearsal and are not claimed as MinIO qualification.

Representative findings and reported fixes: Kafka has `CVE-2026-111497`
(`brotli-libs`, `1.2.1-r0`) and `CVE-2026-33845` (`gnutls`, `3.8.13-r0`);
SeaweedFS has `CVE-2026-116587` (`go-jose/v4`, `4.1.6`) and
`CVE-2026-78661` (`x/net`, `0.62.0`); Trino has `CVE-2026-8178`
(`redshift-jdbc42`, `2.2.2`) and `CVE-2026-68494` (`jackson-core`,
`2.18.8` or `2.21.4`); Flink has `CVE-2026-102554` (`guava`, `33.7.2`);
Redis has `CVE-2026-31789` (`libcrypto3`, `3.3.7-r0`). Python slim based
initializer and dbt images each report 50 HIGH Debian findings, many without
a scanner reported fixed version. Airflow has 248 HIGH and 5 CRITICAL, mainly
Debian packages. Its scanner warned that a third-party SBOM may affect
accuracy; the findings cannot be dismissed on that basis. The Spark scan has
152 HIGH and 5 CRITICAL, compared with 126 combined findings in the older
SEC-022 inventory. Trivy also warned that Spark's Ubuntu 20.04 and Redis's
Alpine 3.21 are unsupported, so their scans may be incomplete.

Maintained upstream releases exist for [Kafka](https://kafka.apache.org/downloads/),
[Trino](https://trino.io/download), [Redis](https://redis.io/downloads/) and
[SeaweedFS](https://github.com/seaweedfs/seaweedfs/releases), but no replacement
image has been built, scanned, or tested with CogniFlow. Remediation requires
updated bases and dependencies, digest-matched rescans with zero findings,
then bounded compatibility tests of Kafka wire/topic behavior, S3 checksum
readback, Spark/Delta and Trino/dbt, Flink checkpoints, and Airflow orchestration.
Review the new Spark inventory under SEC-022 before any further local use.
No image was pulled, rebuilt, published, or deployed in this qualification.

**C4 remains stopped at the image-security gate.** This report is image scan
evidence only; it is not runtime, MinIO, 100 GB, or cloud acceptance evidence.
