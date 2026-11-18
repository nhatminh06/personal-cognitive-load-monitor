# Module II C4.5 Airflow remediation

Recorded 2026-11-17. This qualification covers Airflow and the existing
six-task DAG only. It does not qualify Spark or authorize the full Module II
rehearsal.

## Baseline and remediation

The rollback image `cogniflow-airflow:3.3.2` remains available at local image
ID `sha256:6be8cf0965c00f7a4c5df3eb26b729a0145b8ca504f1b680a276bd6bd8cf9b16`.
Trivy reported 248 HIGH and 5 CRITICAL occurrences: 250 OS-package and three
Python findings. The critical packages were SQLite, libxml2, OpenSSH client,
and zlib; 224 findings had no Debian 12 fix. The Python findings were dnspython
2.8.0 and msgpack 1.2.1.

The replacement upgrades Airflow to 3.4.0 and uses Python 3.11.18 on supported
Alpine 3.24.4. The base is pinned by digest, and Airflow dependencies use the
official 3.4.0 Python 3.11 no-provider constraints file with SHA-256
`9dcbdb5f9b36433b961a03aeb718cf5045005edbe558eeb5ff4a70d99eb50c71`.
dnspython is raised to 2.9.2; runtime krb5-libs and zlib are pinned at
1.22.3-r0 and 1.4-r0. Build-only packaging tools are absent from the runtime.
The process runs as UID/GID 50000.

The exact replacement `cogniflow-airflow:c45-patched` local image ID is
`sha256:ae2ef43a79bd744ec3956e5aff2412d7a3af51f4559b0e374376b28c48f986c3`.
It is local, not published or signed.

## Security result

Trivy 0.76.2 used the vulnerability DB updated 2026-11-17 19:04 UTC and Java
DB updated 2026-11-17 00:59 UTC. The complete exact-image OS and Python scan
reported **0 HIGH and 0 CRITICAL**, with no unsupported-OS warning or scan
error. No finding was suppressed. An intermediate candidate was rejected for
two vendored setuptools findings before the build-only packages were removed.

The raw final JSON is retained outside Git at
`~/cogniflow-resource-backups/c45-image-scans/airflow-c45-final.json`; its
SHA-256 is
`78ca4b98d6f7775baae2730f3101272f21166eb3c0b811a91e2a6f1d250f69e5`.

## Isolated compatibility evidence

Fresh preflight measured 6,491,402,240 available bytes, 48,951,296 bytes above
the required gate. Memory PSI averages were 0.00 and the final two vmstat
samples showed no swap-out. Airflow was limited to 640 MiB and its isolated
mock dependencies to 64 MiB.

Database migration and DAG import completed without errors. The test executed
the exact chain `check_source -> validate_input -> spark_bronze_to_silver ->
verify_silver -> dbt_build -> verify_gold_quality`. All six tasks succeeded and
the DAG run completed in 14.386 seconds. A deliberate first Spark HTTP 500 put
that task into `up_for_retry`; it succeeded after the configured ten-second
delay. Endpoint counts were one source check, three Trino statements, and
three runner calls (failed Spark, retried Spark, dbt). Restarting the Airflow
container with the same test-owned volume retained the successful DAG run.

Peak Airflow cgroup memory was 321,961,984 bytes; current post-run mock usage
was 29.59 MiB. The Airflow home volume used 998,487 apparent bytes. All
test-owned containers, volumes, network, and fixture script were removed; no
existing Docker or Kubernetes resource was changed.

## Status

Airflow is qualified for the bounded local rehearsal only while preflight
observes the exact image ID above. Compose uses the non-root image and keeps
the virtual environment separate from the persistent Airflow home. Spark
remains independently blocked by SEC-022, M10.3 remains NO-GO, and neither
restriction is changed here.

Focused rehearsal tests passed 12/12. The full Python suite passed 627 tests
with two skipped and 87.20% coverage (81% required). Ruff, scoped MyPy, the
orchestration Compose render, and `git diff --check` passed. The first
unprivileged full-suite attempt could not use its localhost tracing socket and
was stopped; the identical suite passed with local socket access.
