# Module II Spark exact-image blocker remediation — 2026-11-21

**Classification: `BLOCKED_UPSTREAM_FIX`.** The current Spark-to-Delta-Lake Silver path has no independently actionable, narrowly scoped source remediation supported by the retained evidence. No source, Dockerfile, image reference, dependency lock, schema, or feature behavior was changed. Spark remains security-blocked and was not started.

## Current Module II boundary

| Area | Current evidence-backed status | Boundary |
|---|---|---|
| Kafka ingestion | PASS independently | Exact patched image evidence and current streaming qualification do not establish the batch path. |
| SeaweedFS/S3 and Bronze | PARTIAL | Local storage and older ingestion evidence exist; no current security-cleared Bronze-to-Silver run exists. |
| Flink to Redis | `PASS_STREAMING_INDEPENDENT` | Synthetic Kafka → Flink → Redis only; not full Module II. |
| Spark/Delta Silver | BLOCKED | Exact configured image fails security policy; no real Spark execution is qualified. |
| Trino/dbt Gold | PASS independently | Used a synthetic Delta Silver fixture, not Spark-produced Silver. |
| Airflow | PASS independently | Six-task orchestration used mocks; it is not live pipeline execution. |
| Complete Module II | UNVERIFIED / BLOCKED | Spark prevents a current Bronze → Silver → Gold qualification. |

The newest applicable reports supersede broader interpretations of older rehearsals. Independent component passes are not combined into an end-to-end pass.

## Exact configured runtime and locks

| Property | Active value |
|---|---|
| Compose image | `cogniflow-spark:3.5.5-delta-3.3.2` |
| Retained exact local identity used by the latest scan | `sha256:9f18d58fc659e838087f928517761d01c1129378353627bbef7d6e4199298d8e` |
| Dockerfile | `infra/module2/spark/Dockerfile` |
| Base | `apache/spark:3.5.5-python3` (tag-pinned, not digest-pinned in source) |
| Runtime line | Spark 3.5.5, Scala 2.12, Java 11.0.26, Python 3, Delta 3.3.2 |
| Python additions | boto3 1.37.38, importlib-metadata 8.5.0, delta-spark 3.3.2 |
| External lock | `infra/module2/spark/ivy-manifest.sha256` |
| Ivy closure | Delta Spark/Storage 3.3.2, ANTLR 4.9.3, Hadoop AWS 3.3.4, AWS SDK bundle 1.12.262, WildFly OpenSSL 1.0.7.Final |
| Configuration consumers | Compose; `scripts/module2_e2e_rehearsal.py`; runner Ivy verification; SEC-022 records |

The image tag is the configuration identity. The latest exact scan binds findings to the local image ID above. Earlier reports contain a different historical local ID and do not transfer their security result. There is no separate centralized Spark release-ledger entry; Compose, the rehearsal allowlist/constants, the Ivy checksum manifest, and SEC-022 evidence collectively form the current identity boundary.

## Vulnerability and ownership analysis

The exact configured image scan found **152 HIGH and 5 CRITICAL** occurrences: Ubuntu packages 63/0, Java archives 83/5, and Python packages 6/0. The five critical Java findings were:

| Origin | Package/version | Finding | Scanner-reported fix |
|---|---|---|---|
| Spark distribution / JVM | Netty handler 4.1.96.Final | CVE-2026-75595 | 4.1.137.Final or 4.2.17.Final |
| Hadoop shaded runtime | Avro 1.7.7 | CVE-2024-47561 | 1.11.4 |
| Spark/Hive JVM closure | Derby 10.14.2.0 | CVE-2022-46337 | 10.14.2.1, 10.15.2.1, or 10.16.1.2 |
| Spark/Hadoop JVM closure | ZooKeeper 3.6.3 | CVE-2023-44981 | 3.7.2, 3.8.3, or 3.9.1 |
| Legacy shaded JVM closure | jackson-mapper-asl 1.9.13 | CVE-2019-10202 | none reported |

The Ubuntu 20.04 base is end-of-support and has incomplete detection risk. Python findings exist, but updating the three Dockerfile-installed Python packages cannot remove the OS, Spark, Hadoop, or shaded JVM failures. Delta 3.3.2 itself was not identified as the source of the retained critical findings; its Spark 3.5/Scala 2.12/Hadoop assumptions constrain any replacement.

The supported-line Spark 3.5.9 candidate also failed at 525 HIGH/22 CRITICAL. A Spark 3.5.9 source design still lacks a converged upstream-validated graph: scanner-required Netty exceeds Spark's pin, Hadoop replacement affects shaded Avro and S3A, Derby and ZooKeeper changes alter the dependency closure, and legacy Jackson has no reported fix. Blind JAR overlays or deletion would create an unsupported classpath.

The later Spark 4.2.1/Scala 2.13/Java 17 plus Delta 4.4.0 candidate also failed. Its exact linux/amd64 image identity `sha256:3fc555ee223244d97fb94f03421d637e7c063c649e733cb195926e0d29644c60` had 579 HIGH/24 CRITICAL. The build-matched Hadoop 3.5.0 S3A closure separately had 15 HIGH/1 CRITICAL, all gate-relevant findings in AWS SDK bundle 2.35.4. Notable fixes included Netty 4.2.17.Final for the image critical and Netty beyond the bundle's 4.1.126, but independently replacing Hadoop's matched AWS bundle is not validated. That candidate also retained provenance and scan-coverage gaps.

## Remediation decision

A Dockerfile-only OS refresh, Python bump, direct-JAR overlay, security suppression, or scan-result transfer cannot meet the existing zero-HIGH/zero-CRITICAL gate while preserving compatibility and provenance. Spark 4 is a Scala, Delta, Hadoop, and object-storage migration, not a narrow correction, and its evaluated candidate still fails.

Therefore no code change is defensible offline. The smallest viable path is a concrete upstream/vendor-supported Spark distribution and S3A closure that supplies patched, converged dependencies. If CogniFlow later owns a source build, it must start with verified Spark/Hadoop/Delta sources and reproducible locks, prove strict dependency convergence and shaded contents, and only then cross the runtime boundary below.

The existing processing contract remains untouched: `jobs/bronze_to_silver.py`, Silver schema/fields, feature ratios, object-storage paths, runner interface, Trino/dbt consumers, and compiled/integration fixtures were not modified.

## Runtime boundary and prerequisites

No build or scan was authorized here. A future candidate requires all of:

1. an upstream-supported Spark/Scala/Java/Hadoop/Delta/S3A version matrix with exact source and artifact provenance;
2. digest-pinned builder and minimal runtime bases plus locked external artifacts;
3. an authorized isolated image build, without touching retained environments;
4. a fresh exact-image OS/language/JVM scan and scan of every external runtime artifact, with zero HIGH and zero CRITICAL and no suppressions;
5. SBOM, shaded/duplicate-class and strict dependency-convergence review;
6. only after the security gate passes, separate Spark/Delta/S3A contract, Silver schema, cross-engine feature-semantics, failure, persistence, and bounded-resource qualification.

Historical image scans cannot qualify the new digest. SEC-022 remains limited to its recorded isolated local scope and does not authorize this work or GKE.

## Validation and files changed

No application or deployment source changed, so Spark tests, the full regression suite, Ruff, and Compose runtime validation were intentionally not rerun. Static review and evidence reconciliation were performed; `git diff --check` was run for this milestone. This report does not characterize static inspection as Spark execution.

Tracked files added by this milestone:

- `docs/readiness/module1-kfp-freeze-decision-2026-11-21.md`
- `docs/security-audit/module2-spark-exact-image-blocker-remediation-2026-11-21.md`

Checksummed, sanitized task evidence is retained under ignored `build/security-scans/kfp-freeze-spark-remediation-2026-11-21/`. Existing source changes and historical reports were preserved.

## Owner action

Track an upstream or vendor-supported candidate whose published dependency graph addresses both the Spark distribution and build-matched S3A closure. Do not schedule another offline preparation milestone until such a candidate exists. At that point, explicitly authorize an isolated build-and-scan milestone; functional Spark execution remains a later, separate gate.

**Final result: `BLOCKED_UPSTREAM_FIX`. `DEFER_KFP` and `DEFER_SPARK_ENFORCED` remain in force.**
