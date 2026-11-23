# Module II independent Spark security qualification — 2026-11-21

## Decision

**BLOCKED.** No required Spark runtime image meets the mandatory zero-HIGH,
zero-CRITICAL gate. Real Spark was not started or invoked. Spark is not
security-cleared, and independent local Spark execution qualification must not
begin.

This audit is local-only. It does not qualify full Module II integration,
Kubernetes, GCP, production, or deployment. SEC-022 was not changed, extended,
or used to bypass the gate.

## A. Current Spark image inventory

The local Compose batch profile has one Spark runtime image. Local mode uses
that same process for driver and executor work; there is no separate worker
image. Six checksum-pinned Ivy artifacts are mounted separately and are part of
the runtime dependency boundary, but are not container images.

| Role | Image | Exact local identity | Architecture | Runtime versions | User |
| --- | --- | --- | --- | --- | --- |
| Configured runtime | `cogniflow-spark:3.5.5-delta-3.3.2` | local image ID and local repo digest `sha256:9f18d58fc659e838087f928517761d01c1129378353627bbef7d6e4199298d8e` | linux/amd64 | Spark 3.5.5, Scala 2.12, Java 11.0.26, Python 3, Delta 3.3.2 | `spark`, Compose UID/GID `185:185` |
| Supported compatibility candidate | `spark:3.5.9-scala2.12-java17-python3-ubuntu` | registry/index digest and local image ID `sha256:8901b8427694267ed719f27aa1498815dbd3573efb3cde447246fbff29d07272` | linux/amd64 | Spark 3.5.9, Scala 2.12, Java 17.0.21.1, Python 3 | `spark` |

The configured tag is locally built and has no independently verified remote
registry provenance; its displayed local repo digest is not a publication
attestation. The official candidate was pulled by exact resolved digest for
this audit and removed after evidence collection.

The pinned Ivy manifest contains:

- Delta Spark and Delta Storage 3.3.2;
- ANTLR runtime 4.9.3;
- Hadoop AWS 3.3.4;
- AWS Java SDK bundle 1.12.262;
- WildFly OpenSSL 1.0.7.Final.

Delta's published compatibility table maps Delta 3.3.x to Spark 3.5.x. A Spark
4.x move would therefore require a Delta 4.x and Scala 2.13 migration and is not
a minimal or already-qualified remediation.

## B. Original vulnerabilities and root causes

Trivy 0.76.2 freshly scanned the exact configured image with OS and language
scanners. The vulnerability database was updated `2026-11-21 01:10:48 UTC` and
the Java database `2026-11-21 00:58:42 UTC`.

| Target | HIGH | CRITICAL | Notes |
| --- | ---: | ---: | --- |
| Ubuntu 20.04 packages | 63 | 0 | Base is end-of-support; Trivy warns detection may be incomplete |
| Bundled Java archives | 83 | 5 | Spark/Hadoop transitive dependency set |
| Python packages | 6 | 0 | Includes packages installed by the Python runtime/application layer |
| **Total** | **152** | **5** | 153 occurrences have reported fixes; 4 do not |

Critical findings are:

| CVE | Package | Installed | Scanner-reported fixed version |
| --- | --- | --- | --- |
| CVE-2026-75595 | `io.netty:netty-handler` | 4.1.96.Final | 4.1.137.Final or 4.2.17.Final |
| CVE-2024-47561 | `org.apache.avro:avro` | 1.7.7 | 1.11.4 |
| CVE-2022-46337 | `org.apache.derby:derby` | 10.14.2.0 | 10.14.2.1, 10.15.2.1, or 10.16.1.2 |
| CVE-2023-44981 | `org.apache.zookeeper:zookeeper` | 3.6.3 | 3.7.2, 3.8.3, or 3.9.1 |
| CVE-2019-10202 | `org.codehaus.jackson:jackson-mapper-asl` | 1.9.13 | none reported |

The complete occurrence-level inventory, including every CVE, package,
installed version, severity, target, and fixed version, is retained as
`original-findings.tsv` beside the raw JSON.

The blocker is not a single CogniFlow Python dependency. It is the combination
of an unsupported Ubuntu 20.04 base and the Spark distribution's bundled Java
dependency graph. Updating only the Dockerfile's three Python packages cannot
remove the Spark/Hadoop findings. Deleting or overlaying arbitrary Spark JARs
would create an unverified classpath and is not accepted as remediation.

## C. Remediation evaluation

The smallest supported path preserving the existing contract is Spark 3.5.9
with Scala 2.12 and Delta 3.3.x. The current official Python/Java 17 Ubuntu image
was pulled and scanned before any CogniFlow layer was built or executed.

That candidate fails the gate:

| Target | HIGH | CRITICAL |
| --- | ---: | ---: |
| Ubuntu 22.04 packages | 445 | 17 |
| Bundled Java archives | 80 | 5 |
| **Total** | **525** | **22** |

It has 81 occurrences with scanner-reported fixes and 466 without. Its Critical
inventory includes seventeen `linux-libc-dev` findings, plus the same five
Critical Java components present in the configured Spark line. Adding boto3,
Delta Python metadata, or CogniFlow files cannot make this failing base pass,
so no derived runtime image was built or executed.

Previous repository evidence also rejects:

- the official Spark 4.1.3 image, which had 720 HIGH/CRITICAL occurrences;
- a hardened Spark 3.5.9 experiment, which retained 178 occurrences; and
- a dependency-patched proof, which retained 21 occurrences and failed strict
  Maven convergence.

No finding was suppressed, ignored, downgraded, or accepted. No security policy
or SEC-022 disposition was changed. There is therefore no honest minimal source
change that clears the gate today.

The smallest viable remediation is an upstream or maintained Spark 3.5.x build
that simultaneously provides a supported, patched runtime base and a converged
Spark/Hadoop dependency graph with zero scanner findings. If CogniFlow must own
that work, it requires a reproducible Spark source build, strict Maven
convergence, Spark/Delta/S3A compatibility tests, a regenerated Ivy manifest,
and a fresh exact-image scan. That is a substantive platform rebuild, not a
safe Dockerfile package bump.

## D. Exact-image security scan results

| Image | Exact ID/digest | HIGH | CRITICAL | Gate |
| --- | --- | ---: | ---: | --- |
| Configured Spark 3.5.5 | `sha256:9f18d58fc659e838087f928517761d01c1129378353627bbef7d6e4199298d8e` | 152 | 5 | FAIL |
| Official Spark 3.5.9 candidate | `sha256:8901b8427694267ed719f27aa1498815dbd3573efb3cde447246fbff29d07272` | 525 | 22 | FAIL |

Neither image was run. The configured image remains preserved; only the newly
pulled candidate was eligible for cleanup.

## E. Compatibility and regression results

- Delta 3.3.x / Spark 3.5.x compatibility: supported by the Delta compatibility
  matrix; the 3.5.9 candidate preserves the major/minor contract.
- Focused Airflow runner, authenticated runner, Spark isolation, and Module II
  rehearsal tests: **25 passed**, one deprecation warning.
- Ruff on the DAG and Spark runner/job paths: passed.
- Scoped MyPy on the DAG and Spark runner/job paths: passed.
- Compose render for `lake` plus `batch`: passed. Rendering `batch` alone fails
  correctly because its required `minio` service belongs to the `lake` profile.
- `git diff --check`: passed.
- The supplied baseline remains 701 passed, 2 skipped, 87% coverage. It is not
  represented as a fresh full-suite result for this security-only audit.

No Spark compatibility execution was attempted because both images failed the
security gate.

## F. Resource and isolation observations

The existing Compose controls remain intact: UID/GID 185, read-only root,
read-only Ivy volume, bounded tmpfs, 1792 MiB memory, 1.5 CPU, internal-only
storage/control networks, no published Spark port, no Docker socket, and a
fixed authenticated job runner. These reduce exposure but do not remediate an
image vulnerability and cannot satisfy the zero-finding gate.

Existing Module I/II containers, volumes, clusters, and the configured Spark
image were not modified. No GCP, Kubernetes, Helm, Terraform, registry, or
remote Git operation occurred.

## G. Remaining blockers

1. The configured image has 152 HIGH and 5 CRITICAL findings and an EOL OS.
2. The supported Spark 3.5.9 candidate has 525 HIGH and 22 CRITICAL findings.
3. Spark's bundled Java graph includes vulnerable Netty, Avro, Derby,
   ZooKeeper, and legacy Jackson components.
4. The prior patched dependency proof did not reach zero and failed strict
   convergence.
5. A Spark 4.x/Delta 4.x migration is broad, compatibility-sensitive, and still
   lacks a zero-finding image candidate.

## H. Files changed and evidence

Tracked change from this task:

- `docs/security-audit/module2-independent-spark-security-qualification-2026-11-21.md`

No Spark Dockerfile, Compose, dependency manifest, application, Airflow, or
Trino/dbt behavior was changed because no verified remediation passed the gate.
Pre-existing working-tree changes were preserved.

Raw ignored evidence is under
`build/security-scans/spark-security-qualification-2026-11-21/`:

| Evidence | SHA-256 |
| --- | --- |
| Configured image raw Trivy JSON | `0192ac75c084f7067844b3cf06698e733cb8b1cd41844b3ecb13c1070806aa89` |
| Configured image complete TSV | `8d09dd49bcc4a5ff3abc0558ffc8961b8f6cb3d28039eccfdaee4187b88281b6` |
| Configured image inspect JSON | `febb7b0672aec3a61a767fc8c1d19249f30f74d6c37e7941b5159af7bf0fc0f2` |
| Spark 3.5.9 raw Trivy JSON | `f6c7b364e4ae135d0d9275f7ff3ae9fe58395655c02f35dd958c6abb9ab35ca2` |
| Spark 3.5.9 complete TSV | `beb731bf62beb9bbc6dc2571edcd29017093154f796479a5a9f2274528f704fa` |
| Spark 3.5.9 inspect JSON | `bed7b5f32f3719aa9babeda62f1014421e2666110d470367e94dd9ebff59d7ce` |

The full manifest is `SHA256SUMS` in that directory.

## I. Final decision

**BLOCKED.** Spark is not SECURITY CLEARED. Real local Spark execution and its
independent qualification remain prohibited until every required runtime image
has a fresh scan with zero HIGH and zero CRITICAL findings. Full Module II
integration remains unverified.
