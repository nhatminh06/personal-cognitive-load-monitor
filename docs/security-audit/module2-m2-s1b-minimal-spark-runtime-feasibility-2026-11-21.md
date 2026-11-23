# Module II M2-S1B minimal Spark runtime security feasibility — 2026-11-21

## Decision

**BLOCKED.** A minimal multi-stage runtime is architecturally possible, but no
credible, upstream-supported and converged Spark 3.5.x dependency graph was
identified that can meet the existing zero-HIGH/zero-CRITICAL gate. No image
was built and no Spark process or workload was started.

This milestone stops at feasibility. Spark remains not security-cleared; real
Spark qualification and full Module II integration remain unverified. No
exception, suppression, policy relaxation, Spark 4 migration, cloud, or
deployment operation was used.

## A. Vulnerability root-cause breakdown

The retained exact-image Trivy result for
`cogniflow-spark:3.5.5-delta-3.3.2`, image ID
`sha256:9f18d58fc659e838087f928517761d01c1129378353627bbef7d6e4199298d8e`,
contains 157 HIGH/CRITICAL occurrences:

| Category | HIGH | CRITICAL | Root cause |
| --- | ---: | ---: | --- |
| OS packages | 63 | 0 | EOL Ubuntu 20.04 `linux-libc-dev` |
| Java runtime | 0 | 0 | Trivy reported no separate JRE target finding; this is not proof that every JRE behavior is safe |
| Spark distribution dependencies | 57 | 4 | Spark assembly and embedded/shaded Spark, Parquet, Hive, Mesos, Netty and Jackson content |
| Spark/Hadoop distribution dependencies | 26 | 1 | Vulnerable classes shaded inside `hadoop-client-runtime-3.3.4.jar` |
| Delta/Ivy dependencies | 0 observed | 0 observed | The mounted six-JAR Ivy cache is outside the scanned image; its checksums are retained but no current raw Ivy scan was available |
| Python packages | 6 | 0 | `urllib3` 1.26.20 from the Python application layer |

The complete occurrence inventory is retained in
`build/security-scans/spark-feasibility-2026-11-21/categorized-vulnerabilities.tsv`.
It records category, ownership, severity, CVE, installed version, fixed version,
and artifact path. `package-summary.tsv` aggregates all 42 vulnerable
package/version groups.

The principal dependency duplication is material rather than cosmetic:

- Jackson exists on 2.12.7, 2.13.4/2.13.4.2 and 2.15.2 lines, plus legacy
  Codehaus Jackson 1.9.13.
- Avro 1.11.4 exists as a direct Spark artifact while vulnerable Avro 1.7.7 is
  shaded inside Hadoop client runtime.
- Guava exists as 14.0.1, 30.1.1-jre, and shaded copies.
- Protobuf exists as 3.3.0 and 3.7.1 in embedded/shaded artifacts.
- Two Jetty 9.4 lines and two Curator lines are present.

These duplicates cannot be corrected by placing one newer JAR first on the
classpath when vulnerable classes are shaded into another artifact.

## B. Required and removable runtime components

### Required for CogniFlow's approved path

- Spark core, launcher, SQL, Catalyst, PySpark and Scala 2.12 runtime.
- Spark RPC/shuffle Netty and compression libraries.
- Spark/Delta Jackson and Parquet support for Delta log and Parquet data.
- Delta Spark and Delta Storage 3.3.x plus ANTLR 4.9.3.
- Hadoop common/client API and runtime classes required by Spark.
- `hadoop-aws`, a build-matched AWS SDK, and S3A dependencies.
- Python, boto3/botocore and the fixed authenticated runner.
- A Java runtime supported by Spark 3.5.x; Java 17 is the preferred maintained
  target for a new image.

### Removable from a purpose-built local runtime

- Spark examples, tests, R support and documentation.
- Kubernetes/YARN launch scripts and cluster-manager assets not used by local
  mode.
- Mesos artifacts, because CogniFlow does not use Mesos.
- Optional command-line and remote-console tooling such as JLine telnet support.
- Native artifacts for non-amd64 platforms.

### Potentially removable only with source/profile evidence

- Derby and Hive metastore components: the CogniFlow job does not use an
  external Hive metastore, but Spark SQL packaging and catalog initialization
  must be proven without them.
- ZooKeeper/Curator: not used by the approved job, but pulled by supported
  Spark/Hadoop assembly profiles.
- Spark UI Jetty: the UI can be disabled, but Jetty classes are shaded into
  Spark core; deleting JARs cannot remove those classes.
- Hadoop legacy/shaded classes: S3A needs Hadoop client functionality, so the
  entire client runtime is not removable. A different Hadoop build is required.

No component is classified as safely removable solely because CogniFlow did
not exercise it in historical runs.

## C. Proposed minimal base/runtime architecture

A defensible future design would use three reproducible stages:

1. **Verified source stage** — obtain the Apache Spark 3.5.9 source release and
   signatures/checksums, verify the release key and SHA-512, and retain the
   source commit/release provenance. Spark 3.5.9 remains the final Spark 3.5
   maintenance release and uses Scala 2.12.
2. **Converged build stage** — build Spark from source on Java 17 with only the
   local, SQL, PySpark and required Hadoop profiles. Use `hadoop-provided` or an
   equivalent controlled classpath so the selected Hadoop common/client/AWS
   artifacts form one version family. Require Maven dependency convergence and
   duplicate-class checks before packaging.
3. **Minimal runtime stage** — use a maintained glibc-based minimal Linux image
   with a patched Java 17 JRE and Python 3.11-compatible runtime; install no
   compiler or package manager in the final layer; copy only the proven Spark,
   Python, Delta and S3A runtime closure; run as UID/GID 185 with the current
   read-only and internal-network controls.

A musl/Alpine runtime is not selected without evidence because Spark native
compression, PySpark wheels and JVM native libraries are commonly built and
tested against glibc. A distroless Java-only image is insufficient because the
approved path also needs Python.

The design is reproducible only if every base image is digest-pinned, every
download is signature/checksum verified, the complete resolved graph is
locked, and the final image is rebuilt and rescanned by immutable image ID.

## D. Dependency convergence analysis

The proposed graph is preserved in
`build/security-scans/spark-feasibility-2026-11-21/convergence-proposal.tsv`.
The blocking constraints are:

| Component | Current source/version | Patched direction | Feasibility and risk |
| --- | --- | --- | --- |
| Netty | Spark 3.5.9 pins 4.1.96.Final | Scanner requires versions through 4.1.137.Final depending on CVE | Required by RPC/shuffle; no Spark 3.5.9 upstream validation for this jump |
| Avro | Spark direct 1.11.5; Hadoop runtime embeds 1.7.7 | 1.11.4+ | Direct Spark Avro is clear, but shaded Hadoop Avro requires replacing/rebuilding Hadoop runtime |
| Derby | Spark 3.5.9 pins 10.14.2.0 | 10.14.2.1 is the nearest fix | Patch-line change appears narrow, but neither Spark 3.5.9 nor Hadoop 3.4.3 supplies it |
| ZooKeeper | Spark 3.5.9 pins 3.6.3 | 3.7.2+ | Not used directly; supported removal/profile evidence is missing, and a blind override also changes Curator compatibility |
| Jackson | 1.9.13, 2.12.7, 2.13.4.x, 2.15.2 | Multiple advisory-specific releases; no fix for legacy 1.9.13 finding | Several copies are shaded; one BOM override cannot converge them |
| Hadoop client | Spark and Delta 3.3.2 build against 3.3.4 | Hadoop 3.4.3 is the maintained candidate | Spark supports source builds with another Hadoop version, but Delta and S3A compatibility would need new proof |
| Hadoop AWS/S3A | 3.3.4 | 3.4.3 candidate | Must exactly match Hadoop common/client artifacts |
| AWS SDK | v1 bundle 1.12.262 | Hadoop 3.4.3 qualifies SDK v2 2.35.4 | This is an API generation change; Hadoop warns not to drop in an arbitrary SDK |
| Delta Lake | 3.3.2 | Remain on 3.3.x | Delta documents 3.3.x as compatible with Spark 3.5.x, but its build also pins Hadoop 3.3.4 |
| Python urllib3 | 1.26.20 | 2.8.0 clears the retained advisories | Feasible only through a fresh boto3/botocore resolution and `pip check` |

Upstream evidence:

- [Spark 3.5.9's POM](https://github.com/apache/spark/blob/v3.5.9/pom.xml)
  pins Hadoop 3.3.4, Netty 4.1.96.Final, ZooKeeper 3.6.3, Derby 10.14.2.0,
  Codehaus Jackson 1.9.13 and Jackson 2.15.2.
- [Spark's build documentation](https://github.com/apache/spark/blob/v3.5.9/docs/building-spark.md)
  supports selecting a Hadoop version and a `hadoop-provided` build, making a
  source experiment technically possible but not automatically compatible.
- [Hadoop S3A troubleshooting](https://github.com/apache/hadoop/blob/trunk/hadoop-tools/hadoop-aws/src/site/markdown/tools/hadoop-aws/troubleshooting_s3a.md)
  requires matching Hadoop artifacts and warns that an AWS SDK upgrade must be
  made with the version Hadoop was built against.
- [Hadoop 3.4.3's POM](https://github.com/apache/hadoop/blob/rel/release-3.4.3/hadoop-project/pom.xml)
  improves Avro, ZooKeeper, DNSJava and Netty relative to 3.3.4, but still pins
  Netty 4.1.127.Final and Derby 10.14.2.0, below this scan's required fixes.
- [Delta's compatibility matrix](https://docs.delta.io/releases/) supports
  Delta 3.3.x with Spark 3.5.x, while
  [Delta 3.3.2's build](https://github.com/delta-io/delta/blob/v3.3.2/build.sbt)
  pins Hadoop 3.3.4 and ANTLR 4.9.3.

This graph is not converged. Netty, Derby, legacy Jackson and embedded Hadoop/
Parquet classes remain blockers even after selecting the newest compatible
Spark and Hadoop maintenance lines.

## E. Candidate build results

No candidate was built. This is deliberate, not an unavailable result.

Previously failed experiments were not repeated:

- official Spark 3.5.9: 525 HIGH, 22 CRITICAL in the fresh retained scan;
- the retained Java 17 official-base experiment: 1,684 HIGH, 95 CRITICAL;
- the retained OS-updated experiment: 528 HIGH, 22 CRITICAL;
- the earlier hardened Spark 3.5.9 experiment: 178 combined occurrences;
- the earlier dependency-patched proof: 21 occurrences and failed strict
  convergence.

The newly analyzed upstream POMs still pin versions below the scanner fixes.
Rebuilding the same graph on another base would repeat the Java failure, while
forcing overrides would violate the evidence requirements of this milestone.

## F. Exact-image security scans

No new image exists to scan. Retained exact evidence used here:

| Evidence | Exact image/result | SHA-256 |
| --- | --- | --- |
| Configured Spark 3.5.5 raw JSON | `sha256:9f18d58f...`; 152 HIGH, 5 CRITICAL | `0192ac75c084f7067844b3cf06698e733cb8b1cd41844b3ecb13c1070806aa89` |
| Official Spark 3.5.9 raw JSON | `sha256:8901b842...`; 525 HIGH, 22 CRITICAL | `f6c7b364e4ae135d0d9275f7ff3ae9fe58395655c02f35dd958c6abb9ab35ca2` |
| Java 17 official-base experiment | 1,684 HIGH, 95 CRITICAL | `49a129a3e38d17d26248283e0f3325bca24e7722728246f97990cd8c18246ed7` |
| OS-updated experiment | 528 HIGH, 22 CRITICAL | `c23a33f323e3444c7b632b4603c239c24acfae81b6ff669784e06f83075cdac4` |

The Ivy manifest SHA-256 is
`d24d4429eace494986a8330700c5dd36de4a1c0632a9a8b49b9faff7b3526d82`.
It proves artifact identity, not vulnerability clearance.

## G. Compatibility risks and missing evidence

- No upstream Spark 3.5.x release validates Netty 4.1.137.Final.
- Hadoop 3.4.3 changes the S3A client from the current Hadoop/AWS SDK v1 stack
  toward AWS SDK v2 and is not validated with CogniFlow or Delta 3.3.2.
- Delta 3.3.2's Spark line is compatible, but its Hadoop 3.3.4 build assumption
  remains.
- Removing Hive, Derby, ZooKeeper, Mesos and remote-console artifacts needs a
  source-profile dependency closure and class-loading proof.
- Shaded vulnerable classes in Hadoop client runtime, Spark core and Parquet
  cannot be fixed through ordinary dependency mediation.
- The retained Ivy artifacts lack a current raw standalone Trivy report in the
  accessible evidence directory.
- No candidate has passed Maven convergence, duplicate-class analysis, full
  Trivy scanning, or subsequent Spark/Delta/S3A functionality qualification.

## H. Remaining blockers

1. There is no converged Spark 3.5.x upstream graph at the scanner-required
   Netty, Jackson, Derby and Hadoop levels.
2. At least one Critical legacy Jackson finding has no scanner-reported fixed
   version and must be removed with its owning module, not overridden.
3. Required S3A artifacts cannot be upgraded independently.
4. The latest maintained Hadoop candidate still pins versions below current
   security fixes.
5. A custom source build would be a maintained platform fork and needs broader
   compatibility evidence than this feasibility milestone permits.

## I. Recommended implementation approach

Do not implement a Dockerfile-only override. Track an upstream Spark 3.5.x or
vendor-supported distribution that incorporates the required dependency fixes.
If ownership accepts maintaining a fork, open a separate bounded source-build
milestone with these gates, in order:

1. lock and verify Spark 3.5.9 and Hadoop 3.4.3 sources;
2. define the minimal module/profile closure;
3. update dependencies in their owning source builds, not by runtime overlay;
4. pass Maven convergence and duplicate-class checks;
5. package on a digest-pinned maintained Java 17/Python base;
6. scan the exact image and the external Delta/S3A closure to zero HIGH and
   CRITICAL;
7. only then begin a separate functional Spark/Delta/S3A qualification.

No production manifest should change until steps 1–6 pass.

## J. Final decision

**BLOCKED — no credible compatible zero-vulnerability approach is currently
demonstrated.** A custom source runtime is theoretically constructible, but the
available supported versions do not form a converged, zero-finding Spark 3.5.x
graph. Spark remains not security-cleared, and no real Spark execution is
authorized by this report.
