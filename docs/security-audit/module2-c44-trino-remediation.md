# Module II C4.4 Trino remediation

Recorded 2026-11-17. This qualification covers Trino, Delta Lake, S3 access,
and dbt compatibility only. It does not qualify Airflow or Spark and does not
authorize the full Module II rehearsal.

## Baseline and remediation

The rollback image `trinodb/trino:478` remains available at registry/local ID
`sha256:177bda76e5e6caf235de4502e10020a029d06dd2625709fbf5adf264b6295a1d`.
Trivy found 119 HIGH and 8 CRITICAL occurrences: 99 in bundled Java
dependencies and 28 in the Go launcher, with no Red Hat OS-package findings.
Critical dependencies included Redshift JDBC 2.2.0, Netty 4.2.7.Final, Kafka
clients 4.1.0, Ranger 2.7.0, Bouncy Castle 1.82, FreeMarker 2.3.28, and Go
1.25.2. Two LZ4 1.8.0 findings had no scanner-listed fix.

The replacement keeps the supported Trino SQL engine and upgrades to official
Trino 484 pinned at
`sha256:2704eb53935af5e582d63d6033e9bf99d20c325e9b0e30b1016ef59a4773979f`.
It uses zero-finding UBI 10.1 pinned at
`sha256:5af8e51abe2a81b4247f05219284a627d37fb9ccf1055b90528a246fac11bc4d`.
The same Airlift launcher 321 is rebuilt from its checksum-pinned source with
Go 1.27.3 and `golang.org/x/text` 0.41.0. Unused Iceberg, lakehouse, Ranger,
and keystore-secret plugins are removed; the Delta Lake connector remains.

The resulting `cogniflow-trino:c44-patched` local image ID is
`sha256:7e24d2c127be225318e5bd7e01e861893e37589829452f97a5d0b467beae34cf`.
It is an amd64 local image and is not published or signed.

## Security result

Trivy 0.76.2 used the vulnerability DB updated 2026-11-17 19:04 UTC and Java
DB updated 2026-11-17 00:59 UTC. The complete exact-image scan detected Red
Hat 10.1 and reported **0 HIGH and 0 CRITICAL** for 95 OS packages, all Java
archives, and the Go launcher. There was no unsupported-OS warning, scan error,
or possible intersection with the CISA KEV inventory because the result set
was empty. No finding was suppressed.

The raw JSON is retained outside Git at
`~/cogniflow-resource-backups/c44-image-scans/trino-c44-patched-final.json`;
its SHA-256 is
`2bf964e7751a1fe32f56c24b68effa84d0068e1c14922a353aa286a4e12f1e23`.

## Isolated compatibility evidence

The test used dedicated containers, network, volume, loopback ports, and a
three-row synthetic Delta table. S3 readback verified Parquet SHA-256
`02b84d9daefba717c3d5be32062ddcec82fdab683e02751c31ae67c2b63b7666`
and Delta-log SHA-256
`f7c371d21260a4efdb461f3a54feb5c022e150e291b48df95ae81b5eba19320b`.

Trino 484 reached ACTIVE state using the existing catalog, registered the
Delta table, and returned three rows, focus sum 135, average focus ratio
0.7666666666666666, and two sessions. Per-session results were `session-a`:
two events/75 focus minutes and `session-b`: one event/60 focus minutes.

dbt-core 1.11.14 with dbt-trino 1.10.6 completed all 15 models/tests twice.
The second run used incremental `MERGE`; daily rows remained one, session rows
two, and reconciled events three. After restarting Trino, Silver still returned
three rows/focus sum 135 and Gold returned two session rows/three events.
`dbt debug` confirmed the profile, project, adapter, and live Trino connection,
but returned nonzero because the hardened dbt image intentionally contains no
Git executable; no package-fetching operation was required by either build.
The first draft fixture omitted the pipeline-derived `event_date`; that test
failed two models, was discarded, and was rerun with the documented contract.

Peak observed memory was 792.9 MiB for Trino, 134 MiB for transient dbt,
116 MiB for SeaweedFS, and 39.66 MiB for its S3 gateway. The storage volume
held 294,606 apparent bytes at completion. All test-owned containers, network,
volume, and fixture files were removed; both kind clusters were preserved.

## Status

Trino and its dbt/Delta/S3 path are qualified for the bounded local rehearsal
only while the preflight observes the exact image ID above. Compose now builds
that image and uses the Trino CLI for readiness, avoiding a runtime-only curl
dependency. Any rebuild must be rescanned and its local ID updated. Airflow and
Spark remain independent blockers, M10.3 remains NO-GO, and SEC-022 is
unchanged.

Focused Trino/rehearsal tests passed 16/16. The full Python suite passed 626
tests with 2 skipped and 87.20% coverage (81% required). Ruff, changed-code
MyPy, the complete lake-plus-analytics Compose render, and `git diff --check`
passed. A wider MyPy invocation against unchanged `trino_history.py` was not
used as a gate because the environment lacks the existing optional
`types-requests` stubs.
