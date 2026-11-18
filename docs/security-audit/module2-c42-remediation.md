# C4.2 Module II image remediation — 2026-11-17

**Rehearsal decision: NO-GO.** Five image paths were repaired and scanned at
zero HIGH/CRITICAL, but Kafka, Trino, Airflow, and Spark still fail the normal
gate. No full rehearsal, 100 GB workload, cloud deployment, or model operation
was started. This record supplements the exact baseline inventory in
`module2-c41-image-qualification.md`; it does not change SEC-022 or M10.3.

Trivy 0.76.2 used the vulnerability DB updated 2026-11-17 19:04 UTC and Java
DB updated 2026-11-17 00:59 UTC. Every candidate was scanned by its local
image ID with OS and language scanning enabled. The five raw JSON reports and
the CISA KEV snapshot are retained outside Git on persistent disk; their
`SHA256SUMS-C42` manifest has SHA-256
`d268c68c2738f16b3b8b049cd0671b39d1287c4c92660614addb90df5b432e1b`.
Counts below are scanner occurrences, not unique CVEs. Local image IDs are
immutable for these scans; no published registry digest or signature was
created. Rebuilds must be rescanned and their IDs checked again.

| Service image | Original local ID (`sha256:`), HIGH/CRITICAL | Candidate local ID (`sha256:`), HIGH/CRITICAL | Change and verification |
|---|---|---|---|
| SeaweedFS 4.50 | `89fa460d0484b69f16304071fc0415cf5f18be2208814a4360a309cb5c654375`, 2/0 | `7499507f4f3bcc532fffadc3aaca5f2f5146d998409b9ad5af25d5393813591a`, **0/0** | Same verified source commit; `go-jose/v4` 4.1.6 and `x/net` 0.62.0. Version and isolated server health passed; S3 gateway plus initializer wrote/read 17 exact bytes with SHA-256 `ce17389fe28ab7ae6408bd47dc13e0bd68381980e7fb14e0c4bab68364fbb51b`. |
| Bucket initializer | `52463a84ad84178f1614262fdf6c7931c430cdb0a7570160e0b77e150e360bbb`, 50/0 | `9d98869261933b5e730e91ec83817c0f1a4c3d2243ce161ee2bd56ed2d01bfee`, **0/0** | Pinned Python 3.11 Alpine 3.24 base, patched OS packages; UID 10001/import check and creation of both isolated test buckets passed. |
| Flink 1.20.5 | `bafb75f18fb2653bea6a1c819a7e5600c141ff3287b8d8145393e985eff3046a`, 4/0 | `a6dc8622eefc195995f9a03d594200fc7317f374412c842f6d74bae7d5774baa`, **0/0** | Ubuntu packages upgraded and Guava 33.7.2-jre added. Maven tests/package passed during build; CLI reported version 1.20.5 with a bounded writable tmpfs. No streaming checkpoint test was run. |
| dbt 1.11.14 | `98946381d5eddc3417ed54a0a9c7e78134415af193c0e8dd5f80e6754a7cf475`, 50/0 | `9633d2fadfb95ff558461a40d92bbce8b73ffca8745a5c8b7a81e5bef522ed95`, **0/0** | Pinned Python 3.11 Alpine 3.24 base; build tools removed after installation. `pip check` and network-disabled `dbt parse` against the read-only project passed. No live Trino build was run. |
| Redis 7.4 | `02419de7eddf55aa5bcf49efb74e88fa8d931b4d77c07eff8a6b2144472b6952`, 78/6 | `7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe`, **0/0** | Official 7.4.12 Alpine 3.22 patch image. Isolated authenticated PING, SET, and Lua EVAL passed. No persistent volume was mounted. |

The old images were not deleted. Compose now names the five candidate tags,
while the preflight checks their exact local IDs and resolved image inventory.
The source changes do not imply that a rebuild will have the same ID: Python
transitive packages and Alpine repository state can move. The preflight fails
closed if an ID or Compose image changes. Its focused tests passed **23/23**;
Ruff, scoped MyPy, full-profile Compose render and `git diff --check` passed.
An actual dry-run of `scripts/module2_e2e_rehearsal.py` exited 1 and named
Kafka, Trino, Airflow and Spark as unqualified, without starting services.
Smoke containers and the temporary internal network were removed, and both
kind clusters and existing Docker volumes were preserved.

The baseline package-level evidence explains the changes: SeaweedFS carried
`go-jose/v4` 4.1.5 (fixed 4.1.6) and `x/net` 0.61.0 (fixed 0.62.0); Flink
carried `apt` 2.4.14 (fixed 2.4.15ubuntu0.1), `libbrotli1`
1.0.9-2build6 (fixed 1.0.9-2ubuntu0.1), and Guava 32.1.2-jre (fixed
33.7.2). The initializer and dbt Debian bases shared `apt` 3.0.3
(fixed 3.0.4) and `bsdutils` findings without reported fixes; neither
application's Python packages were flagged. Redis 7.4.2 Alpine had vulnerable
OpenSSL packages and a bundled Go `stdlib` 1.18.2 in `gosu`; the official
7.4.12 image scan found neither package finding.

## Remaining images and local risk

| Image | Current HIGH/CRITICAL; fixable/unfixed | Exposure and next safe remediation |
|---|---|---|
| Kafka 3.9.2 `sha256:05b4616e0702ef2729327705d54ad6b50ea70b271c4b730fabd2320789fb7b02` | **67/7; 74/0** | Alpine OS packages plus Kafka Java dependencies, including Jackson and Netty. Broker accepts synthetic traffic on an isolated local network and loopback port; `CVE-2026-111497` in Brotli is on CISA's known-exploited list. A same-contract patched image and topic/offset/restart tests are required. No blanket exception is proposed. |
| Trino 478 `sha256:177bda76e5e6caf235de4502e10020a029d06dd2625709fbf5adf264b6295a1d` | **119/8; 125/2** | Mostly Java and bundled Go dependencies, including Redshift JDBC, Jackson and Guava. The query endpoint is loopback-published during local use; a maintained release exists, but connector compatibility with Delta/dbt must be verified before replacement. |
| Airflow 3.3.2 `sha256:6be8cf0965c00f7a4c5df3eb26b729a0145b8ca504f1b680a276bd6bd8cf9b16` | **248/5; 29/224** | Primarily Debian OS packages; three Python findings. The local development profile launches an orchestration process with access to fixed job runners. Its broad unfixed inventory is unsuitable for an automatic exception. A patched compatible base and six-task DAG test are required. |
| Spark 3.5.5/Delta 3.3.2 `sha256:d55eac37429cb0d94208d79fcae0f1002662b1d9700eb1b4a522bbe6cf2bb0e8` | **152/5; 153/4** | SEC-022 remains local-only for this exact ID and fixed job. New scan inventory exceeds the older 126 combined finding record, and Ubuntu 20.04 is unsupported by the scanner. Two `linux-libc-dev` CVEs intersect CISA KEV but describe host kernel/USB paths rather than a demonstrated Spark application path; Java findings remain potentially reachable through Spark/Delta/S3A. Owner review is required before local reuse; no exception was broadened. |

Representative fixed versions for the remaining images: Kafka's Brotli
1.2.0-r0 has fix 1.2.1-r0 and GnuTLS 3.8.11-r0 has fixes from 3.8.12-r0;
its Jackson databind 2.16.2 has fixes on newer 2.18/2.21 lines. Trino's
Redshift JDBC 2.2.0 has fix 2.2.2 and Jackson core 2.20.0 has fixes on
2.21/2.22 lines. Airflow's Python `dnspython` 2.8.0 has fixes 2.9.0/2.9.2
and `msgpack` 1.2.1 has fix 1.2.3; its Debian `rsync` 3.2.7-1+deb12u6
has fix 3.5.0+ds1-0+deb12u1. Spark's Python `urllib3` 1.26.20 and multiple
older Jackson copies have scanner-reported fixes; Ubuntu `linux-libc-dev`
5.4.0-208.228 has fixes through 5.4.0-216.236. The complete dependency and
fixed-version lists remain in the baseline JSON scan artifacts.

The [CISA KEV catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
snapshot was released 2026-11-17 17:53 UTC. Intersection found one baseline
Kafka CVE and two Spark package CVEs; the baseline Flink Brotli CVE was removed
in the patched candidate. Absence from KEV is not evidence that exploitation
is impossible. Trivy warned that the old Redis Alpine 3.21 and Spark Ubuntu
20.04 scans may be incomplete. No CVE was suppressed.

Upstream maintains newer [Kafka](https://kafka.apache.org/downloads/),
[Trino](https://trino.io/download), and [Redis](https://redis.io/downloads/)
releases, but only the Redis 7.4 patch image was qualified here. A newer major
or rolling service release is not presumed compatible. The remaining four
images need exact candidate builds or pulls, complete scans, and local
contract tests; Spark additionally needs SEC-022 owner review. A local-only
educational exception could be considered only for a specific reviewed image
and bounded exposure, never as a blanket override or deployment approval.

**C4 cannot run yet.** The next executable security work is a compatible
Kafka candidate with patched OS and Java libraries, followed by an exact scan
and broker/topic/offset test. The Trino, Airflow, and Spark blockers remain
independent. MinIO, >100 GB processing, and cloud acceptance remain incomplete.
