# Module II M2-S1D — Spark 4 security candidate qualification

**Date:** 2026-11-21

**Decision:** **BLOCKED**

**Scope:** isolated security-only qualification of Apache Spark 4.2.1 with
Delta Lake 4.4.0. No Spark process, driver, executor, Delta workload, S3A
request, Airflow integration, cloud operation, or production deployment ran.

## Executive result

The exact official linux/amd64 Spark 4.2.1, Scala 2.13, Java 17, Python 3
image fails the existing zero-HIGH/zero-CRITICAL gate:

| Scanned artifact | HIGH | CRITICAL | Result |
| --- | ---: | ---: | --- |
| Official Spark 4.2.1 image: OS packages | 520 | 21 | FAIL |
| Official Spark 4.2.1 image: Java packages | 59 | 3 | FAIL |
| Hadoop 3.5.0 candidate external JAR set | 15 | 1 | FAIL |

The image total is **579 HIGH and 24 CRITICAL occurrences**. The external set
contains the direct Delta 4.4.0 and Hadoop AWS 3.5.0 artifacts and the exact
AWS SDK v2 bundle required by Hadoop. Its 15 HIGH and one CRITICAL findings are
in `software.amazon.awssdk:bundle:2.35.4`.

This is not an OS-only failure. Required Spark and S3A components contain
critical vulnerable versions, including Netty 4.2.13 in Spark and Netty
4.1.126 inside the Hadoop-matched AWS SDK bundle. A derived runtime was not
built because an OS refresh cannot remediate those upstream-owned closures,
and arbitrary version overlays would violate this milestone's compatibility
and provenance requirements.

Spark remains **not security-cleared**. Real Spark execution and full Module II
integration remain **BLOCKED/UNVERIFIED**.

## A. Preflight and isolation

The M2-S1B feasibility report and M2-S1C architecture decision were read first.
The existing working tree contained one modified source file and five untracked
audit reports. They were preserved without alteration.

Initial host capacity:

- memory: 15 GiB total, 8.5 GiB available;
- swap: 15.3 GiB total, 13 GiB free;
- disk: 147 GiB available on the repository filesystem;
- Docker: 15 images, nine containers (six running), nine volumes, and seven
  networks;
- pre-existing Docker storage: 12.7 GB images, 104 MB containers, 5.272 GB
  volumes, and 21.73 GB build cache.

No configured CogniFlow Spark image or existing container was started or
modified. The retained `cogniflow-local`/Module I resources and all Module II
Kafka, Flink, Redis, SeaweedFS, Trino, and Airflow resources were untouched.

Task ownership was limited to:

- the ignored directory
  `build/security-scans/spark4-security-candidate-2026-11-21/`;
- the immutable official Spark image pulled by linux/amd64 digest;
- a scratch-only, non-runnable JAR scan carrier image named
  `m2s1d-spark4-jar-scan:2026-11-21`;
- one never-started extraction container named
  `m2s1d-spark4-static-extract`.

## B. Exact candidate inventory

### Official image

| Property | Observed value |
| --- | --- |
| Tag queried | `apache/spark:4.2.1-scala2.13-java17-python3-ubuntu` |
| Multi-architecture index | `sha256:c0e6770a7c500d3f1090c9b9f4e26cb5914aec987a94cd44cae1eb1f65b0fa51` |
| linux/amd64 manifest and local image ID | `sha256:3fc555ee223244d97fb94f03421d637e7c063c649e733cb195926e0d29644c60` |
| OS / architecture | linux/amd64 |
| Uncompressed size | 2,131,949,791 bytes |
| Base OS reported by Trivy | Ubuntu 22.04 |
| Configured user | `spark` (non-root name) |
| Java | `jdk-17.0.20.1+1` |
| Python OS packages | Python 3.10.12 runtime; distro `python3` metadata 3.10.6; pip 22.0.2 |
| Spark distribution | 4.2.1 binary for Hadoop 3 |

Docker configuration inspection established the configured non-root user but
did not execute the image, so effective UID, writable paths, and runtime
permissions were not dynamically tested.

### Candidate-only Maven artifacts

The candidate graph was anchored to these exact coordinates:

- `io.delta:delta-spark_2.13:4.4.0`;
- `io.delta:delta-storage:4.4.0`;
- `io.delta:delta-kernel-api:4.4.0`;
- `io.delta:delta-kernel-defaults:4.4.0`;
- `io.delta:delta-kernel-unitycatalog:4.4.0`;
- `org.apache.hadoop:hadoop-aws:3.5.0`;
- `software.amazon.awssdk:bundle:2.35.4`;
- `software.amazon.s3.analyticsaccelerator:analyticsaccelerator-s3:1.3.1`;
- `org.wildfly.openssl:wildfly-openssl:2.2.5.Final`.

Local SHA-256 values for the JARs:

| Artifact | SHA-256 |
| --- | --- |
| Delta Spark | `27d4fd8b1f879535c573ed1c718177d6a27f24d3e626ba02e216369725721ead` |
| Delta Storage | `c46735481fa8e326b0957be02b4420cbcab4b325bb08009b7f2045a95133f1cc` |
| Delta Kernel API | `ee9b5a14ac3b7efdff4d61a58478fe8eb0e5a3fbca43889dca7290795fe79a11` |
| Delta Kernel Defaults | `225c975199e4718b38ee5b7e6da7f19e9585024262b2cec2656b32151a856b0b` |
| Delta Kernel Unity Catalog | `cea22dfb4ac562b3cd27bf652697750e8336009d73fb06631363aaaad5345ffa` |
| Hadoop AWS | `66bd9eefb938b1a1657487324b63c13df2d8b17164a1dd24e0ef37b905bc5baa` |
| AWS SDK v2 bundle | `db4b55f24ad1b4e70f17eb1717a4de76a8dadc5a27d764be7c44ff67b2c1c677` |
| S3 Analytics Accelerator | `4959a9747cbb479c73c3ffbcd479bee5b014f8b2880994585a8693fb9d24675e` |
| WildFly OpenSSL | `71fb7932f99a727edb23c5a2cb8c6855ac7196fad41aa0669b3998e277165154` |

The complete sizes and hashes, including POMs and detached signatures, are in
`artifact-sizes.tsv` and `artifact-sha256.txt`.

## C. Artifact provenance

The image was obtained by immutable linux/amd64 digest from the Apache Spark
Docker Hub repository. The registry published an SLSA provenance attestation
whose source is `https://github.com/apache/spark-docker` at revision
`51ab904ef98dbac2365b90edeea2315e42348941`. The raw OCI index and attestation
are retained. The registry digest was verified by Docker during pull; no
separate Sigstore identity policy was available or asserted.

The Maven artifacts came from Maven Central over HTTPS. Detached OpenPGP
verification produced:

- good cryptographic signatures for all five Delta 4.4.0 JARs using subkey
  `168412826F69D8C494EE0C46F428C01CA69D764A`;
- a good signature for Hadoop AWS 3.5.0 using Apache code-signing fingerprint
  `3EC9157CB0281495A6E7FC9F1105854687CDDA79`;
- a good signature for AWS SDK bundle 2.35.4 using fingerprint
  `FEB9209F2F2F3F4664841E55AC107B386692DADD`;
- the Analytics Accelerator signature could not be checked because public key
  `78A98B68BAB3E22E` was not retrieved;
- Maven Central did not expose the requested detached signature for WildFly
  OpenSSL at the expected artifact URL.

The task-owned GPG keyring confirms signature integrity only; the downloaded
keys were not independently elevated to an organizational trust root. These
two unresolved signature cases are provenance gaps and independently prevent a
full PASS, even without the vulnerability failures.

Authoritative sources used:

- [Apache Spark 4.2.1 release](https://spark.apache.org/releases/spark-release-4-2-1.html)
- [Spark 4.2.1 POM](https://github.com/apache/spark/blob/v4.2.1/pom.xml)
- [Apache Spark official image tags](https://hub.docker.com/r/apache/spark/tags)
- [Delta 4.4.0 build definition](https://github.com/delta-io/delta/blob/v4.4.0/build.sbt)
- [Delta 4.4.0 Spark-version definitions](https://github.com/delta-io/delta/blob/v4.4.0/project/CrossSparkVersions.scala)
- [Maven Central](https://repo.maven.apache.org/maven2/)

## D. Dependency convergence

The official image contains Spark 4.2.1 with Scala 2.13.18 and Hadoop client
API/runtime 3.5.0. Delta Spark 4.4.0 publishes for Scala 2.13 but declares
Scala 2.13.17 and Spark core/SQL/Catalyst/Hive 4.2.0 as `provided`. This is
binary-line alignment, not proof that Spark 4.2.1 was the exact tested runtime.

Delta Storage declares Hadoop common and Hadoop AWS 3.4.2 as `provided`.
Consistent with M2-S1C, those declarations were not used to substitute Hadoop
3.4.2 into the Spark 4.2.1 runtime. Spark's Hadoop 3.5.0 remains authoritative.

Hadoop AWS 3.5.0's POM and parent resolve the S3A runtime to:

- AWS SDK v2 bundle 2.35.4 (compile);
- S3 Analytics Accelerator 1.3.1 (compile);
- WildFly OpenSSL 2.2.5.Final (runtime);
- AWS SDK v1 core 1.12.720 only as `provided` for legacy credential-provider
  adapters, and therefore not selected for the current standard credentials.

No unsupported override was applied. In particular, the vulnerable AWS SDK
bundle was not independently replaced because Hadoop requires its build-matched
SDK closure.

The Delta POM also makes Delta Kernel API, defaults, and Unity Catalog modules
compile dependencies. Their direct JARs were retained and scanned. A complete
transitive Maven resolution was not promoted as a runnable candidate because
the base Spark image and required AWS bundle had already failed the gate.
Consequently, this work does not claim full runtime-artifact coverage.

## E. Original and candidate security findings

Trivy was refreshed before scanning:

- scanner: Trivy 0.76.2;
- vulnerability DB schema 2, updated `2026-11-21T01:10:48Z`;
- Java DB schema 1, updated `2026-11-21T00:58:42Z`;
- no ignored CVEs, suppression file, severity downgrade, or exception was used.

### Exact official image

The image has 520 HIGH/21 CRITICAL OS occurrences and 59 HIGH/3 CRITICAL Java
occurrences. Material Java blockers include:

| Package | Installed | Finding | Fixed version reported by Trivy |
| --- | --- | --- | --- |
| `io.netty:netty-handler` | 4.2.13.Final | CVE-2026-75595, CRITICAL | 4.2.17.Final |
| `org.apache.derby:derby` | 10.16.1.1 | CVE-2022-46337, CRITICAL | 10.16.1.2 |
| Jackson core/databind | 2.18.6, 2.19.2, 2.21.2 | multiple HIGH | advisory-specific 2.18.8-11 / 2.21.4-7 / 2.22.x |
| Netty modules | 4.2.13.Final | multiple HIGH | 4.2.15-16.Final or later |
| `com.google.guava:guava` | 33.4.8/33.6.0-jre | CVE-2026-102554, HIGH | 33.7.2 |
| `org.apache.thrift:libthrift` | 0.16.0 | two HIGH | 0.23.0/0.24.0 |
| `org.eclipse.jetty` | 9.4.58 / 12.1.8 | HIGH | 9.4.60 / 12.1.10 |
| `at.yawk.lz4:lz4-java` | 1.11.0 | CVE-2026-106451, HIGH | 1.11.4 |
| `org.xerial.snappy:snappy-java` | 1.1.10.8 | two HIGH | 1.1.10.9 |

The three Java critical occurrences are Netty in its standalone JAR and
Spark Connect client JAR, plus Derby. OS critical findings are predominantly
`linux-libc-dev` 5.15.0-202.212; most had no fixed version in the current
Ubuntu advisory data, while a subset reported 5.15.0-203.213/204.214 fixes.

### Candidate-only external JARs

The external scan found 486 Java packages and 32 total vulnerability
occurrences. The gate-relevant 15 HIGH and one CRITICAL occurrence all map to
the 654.3 MiB AWS SDK v2 bundle 2.35.4:

- Netty 4.1.126: fourteen HIGH occurrences and CVE-2026-75595 CRITICAL;
- AWS CloudFront 2.35.4: GHSA-443w-3rq3-5m5h HIGH, fixed in 2.41.30.

The direct Delta, Hadoop AWS, Analytics Accelerator, and WildFly JARs did not
produce HIGH/CRITICAL results in this scan. That limited result must not be
interpreted as a clean complete transitive Delta/S3A runtime.

## F. Image and standalone JAR scan results

Raw reports and their SHA-256 values:

| Evidence | SHA-256 |
| --- | --- |
| `trivy-base-image.json` | `5be66a1ea03cd507cf59b92c90a9edfdb2ceb8e602f02d160df24ad38d169633` |
| `trivy-external-jars.json` | `8f5d63b292f2ea7634bf3b8f5c7bfa2fc7d310567ab04939ed16be225acdce31` |
| `official-image-index.json` | `c0e6770a7c500d3f1090c9b9f4e26cb5914aec987a94cd44cae1eb1f65b0fa51` |
| `official-image-provenance.json` | `ccfae689e80e3d4183799e74605d702d9bc9410df240f73645351c0fcc441659` |
| `base-package-inventory.tsv` | `ee6390c658707bd619961f99d73b6e05454df7cb0bdbc9d994e4ebf266b5131d` |
| `duplicate-classes.tsv` | `70ffd9697258dc409e33918eb60da121f99d6e2dbcddd6d1972537278f4962be` |

Trivy filesystem mode did not identify standalone JARs directly. A scratch
carrier containing only the exact artifact files was built so the image JAR
analyzer would inspect them. It had no executable, was never run, and was not
a Spark candidate. Its metadata was retained before deletion.

Coverage gaps:

- Trivy produced OS and Java targets for the official image but no independent
  Python language-package target. Distro Python/pip packages are inventoried;
  PySpark source under the Spark distribution is not equivalent to a scanned
  installed wheel dependency graph.
- Embedded/shaded components are reported where Trivy recognized package
  metadata. Absence of metadata is not proof that every shaded class was
  independently identified.
- The full transitive Delta Kernel/Unity Catalog graph was not materialized
  after required base/S3A components failed.

These gaps would prevent PASS even if the observed findings were zero.

## G. Duplicate and shaded dependency analysis

The official image contains at least these parallel version families:

- Jackson core/annotations/databind 2.18.6, 2.19.2, and 2.21.x;
- Guava 33.4.8-jre and 33.6.0-jre;
- Avro 1.11.5 and 1.12.1;
- Curator 5.2.0 and 5.9.0;
- Jetty 9.4.58 and 12.1.8;
- JLine 3.9.0 and 3.29.0;
- multiple commons-codec, commons-io, commons-lang3, commons-compress,
  servlet, JAXB, and HTTP client lines.

The static class index covered 565,275 class entries and found 4,599 duplicate
class paths. Many come from Spark's existing broad distribution and shaded
Hadoop/Parquet/Spark Connect content. Examples include two JDO APIs and the
Scala compiler embedding Java Diff Utils. Package metadata confirms vulnerable
Jackson, Guava, Avro, and Curator copies inside
`hadoop-client-runtime-3.5.0.jar`, while Parquet embeds another Jackson line.

The candidate-only direct JARs created no ordinary class-path collision with
Spark's JAR directory in this static comparison; the only overlap was a
multi-release `META-INF/versions/9/module-info.class`. The AWS SDK bundle still
contains vulnerable components detected by Trivy. No runtime class-loading
conclusion is possible without execution, and no execution was permitted.

## H. Static compatibility results

| Check | Result |
| --- | --- |
| Spark / Hadoop | Converged at Spark-owned Hadoop client 3.5.0 |
| Spark / Scala | Spark 4.2.1 uses Scala 2.13.18 |
| Delta coordinate | `delta-spark_2.13:4.4.0`, Scala binary line compatible |
| Exact Delta-tested Spark | Delta POM declares provided Spark 4.2.0, not exact 4.2.1; unresolved |
| Delta Hadoop baseline | 3.4.2 is provided/build-time only; not substituted into runtime |
| S3A / AWS SDK | Hadoop AWS 3.5.0 with SDK v2 bundle 2.35.4; version-aligned but security-failing |
| Java | Image provides Java 17.0.20.1, satisfying Spark's Java 17 line |
| Python | Image provides Python 3.10, satisfying Spark 4's stated minimum line |
| Duplicate classes | 4,599 paths found; no candidate-only ordinary collision, substantial existing duplicates/shading |
| Runtime compatibility | UNVERIFIED; static checks cannot establish Spark/Delta/S3A function |

The current CogniFlow job would also require Scala 2.13 Delta coordinates, a
new locked candidate manifest, Spark 4 migration checks, and later S3A commit
behavior qualification. None was applied to production files.

## I. Resource consumption

- official image pull: 2.13 GB uncompressed image;
- retained ignored evidence: approximately 1.2 GiB;
- retained exact Maven artifacts: approximately 671 MiB, dominated by the
  686,119,507-byte AWS SDK bundle;
- extracted Spark JAR evidence: approximately 456 MiB;
- measured cached Trivy base-scan peak RSS: 292,260 KiB;
- first base scan: 11.377 seconds wall, 10.930 user, 1.288 system;
- external JAR scan: 10.260 seconds wall, 5.942 user, 1.218 system;
- final host capacity: 8.7 GiB available RAM, 12 GiB free swap, 142 GiB disk.

No runtime container was started, so container CPU/memory, OOM, and restart
metrics are not applicable. No OOM event or unexpected restart was observed.

Docker build cache changed from 195 records/21.73 GB to 199 records/23.75 GB.
It was not broadly pruned because Docker exposes those cache records in a
shared store and broad pruning could delete pre-existing user evidence. The
increase is reclaimable but is a cleanup limitation.

## J. Remaining blockers

1. The exact official image has 579 HIGH/24 CRITICAL findings.
2. Required Spark Java components include critical Netty and Derby versions.
3. The Hadoop-build-matched AWS SDK bundle independently has 15 HIGH/one
   CRITICAL finding; replacing it independently is unsupported.
4. Spark's shaded Hadoop/Parquet and broad distribution contain multiple
   vulnerable/duplicate dependency lines that cannot be corrected by ordinary
   classpath precedence.
5. Delta 4.4.0 declares Spark 4.2.0 as provided; exact Spark 4.2.1 functional
   compatibility remains unverified.
6. Complete Delta transitive and Python language-package scan coverage was not
   established because required earlier components had already failed.
7. Analytics Accelerator and WildFly OpenSSL provenance verification remains
   incomplete.
8. Static checks cannot establish Delta merge, S3A, object-store, persistence,
   or data-correctness compatibility.

The smallest viable remediation is an upstream Spark maintenance release that
owns compatible Netty, Derby, Jackson, Hadoop/shaded dependency updates plus a
Hadoop maintenance line built against a remediated AWS SDK v2 bundle. A future
candidate must be resolved and scanned as one exact closure; Dockerfile-level
JAR overlays are not defensible.

## K. Cleanup and evidence retention

Removed task-owned Docker resources:

- never-started container `m2s1d-spark4-static-extract`;
- scratch carrier image `m2s1d-spark4-jar-scan:2026-11-21`;
- pulled official image digest
  `sha256:3fc555ee223244d97fb94f03421d637e7c063c649e733cb195926e0d29644c60`.

No volume or network was created. Final inventory remains 15 images, nine
containers, nine volumes, and the same seven networks as preflight. The raw
reports, package inventories, direct POMs/JARs, signatures, class maps,
resource records, and Docker metadata remain under the ignored evidence
directory. `evidence-checksums.sha256` covers the retained evidence files.

## L. Final decision

**BLOCKED.** The exact Spark 4.2.1/Delta 4.4.0 direction cannot satisfy the
zero-HIGH/zero-CRITICAL policy with the observed official Spark and
Hadoop-matched S3A dependency closure. No compatible, fully verified remediation
path was demonstrated, so no derived runtime was built and no Spark image was
executed.

M2-S1C's `DEFER_SPARK` decision remains in force. This result does not qualify
real Spark execution, Delta/S3A functionality, full Module II integration,
cloud readiness, Kubernetes, or production deployment.
