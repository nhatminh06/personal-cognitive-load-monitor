# C17 minimal MySQL runtime qualification

**Date:** 2026-11-19

**Starting revision:** `c22eefc11c22930e7a1fb2fbfeac73cb48111262`

**Decision:** **BLOCKED — the one bounded build produced no candidate image**

No Kubernetes object, protected cluster, cloud resource, registry, or model was
changed. No database container was started because the image prerequisite was
not created.

## KFP 2.18.1 database contract

The exact `platform-agnostic` release manifests select MySQL 8.4 for
`mlpipeline`, `cachedb`, and MLMD's `metadb`. The API server and cache server
use Go MySQL drivers and perform GORM schema migration. MLMD connects over the
MySQL protocol and runs with `--enable_database_upgrade=true`. Persistence and
scheduled-workflow controllers use the KFP API rather than a separate database
client.

The selected manifests and backend source contain no MySQL Shell invocation.
The official container entrypoint requires `mysqld`, `mysql`, `mysqladmin`, and
`gosu`; RPM ownership shows the three MySQL binaries belong to
`mysql-community-server-minimal-8.4.13-1.el9`, not `mysql-shell`. MySQL native
password support is built into MySQL 8.4 and is enabled by the exact KFP flags.
MySQL Shell, its OCI SDK, and its embedded Python runtime are therefore optional
for this KFP database contract.

## Selected distribution and bounded build

The selected approach was a minimal derivative of the exact KFP-pinned official
linux/amd64 image
`mysql@sha256:a81d043930e51745522bd5c430961cf8286f0a23f0a9a2a6e0108f7ea71b0902`.
It retained the official entrypoint and `mysql-community-server-minimal`,
removed the separately packaged `mysql-shell-8.4.10-1.el9`, upgraded only the
four scanner-fixed Oracle Linux libraries to `2.37.4-28.0.1.el9_9`, and rebuilt
real gosu 1.20 from verified revision
`29b939aa5bd4dc588af765b8248f6e39150d2565` with the pinned Go 1.27.4 builder.

The RPM transaction removed exactly one 514.3 MB package and no dependency.
The OS upgrades also succeeded. The final fail-closed inventory assertion then
rejected the filesystem because `/usr/lib/mysqlsh` still existed, so the build
stopped before exporting an image.

Post-failure inspection in an auto-removed disposable container confirmed the
reason: uninstalling the RPM leaves an unowned MySQL Shell directory tree,
including Python standard-library caches and MySQL Shell plugin caches. It
leaves no `.dist-info` or `METADATA`, while the required MySQL 8.4.13 server,
client, and admin binaries remain functional. Deleting that residual tree in a
derived layer could be justified by functionality, but it would require a
second build and risks repeating the C16 metadata-removal ambiguity. It was not
attempted under the one-build limit.

## Qualification status and next packaging strategy

No `cogniflow/mysql:8.4.13-c17-minimal` image exists. Consequently there is no
candidate identity, scan, SBOM, provenance claim, non-root runtime result, or
functional database result. This is BLOCKED rather than NO-GO because the
candidate was never created.

The evidence supports a different packaging strategy for any separately
authorized future work: start from a pinned Oracle Linux base and install the
official `mysql-community-server-minimal` 8.4.13 RPM and its resolved runtime
dependencies directly, so MySQL Shell and OCI/Python files never enter any
layer. That path must pin repository/RPM identities, retain the official
entrypoint behavior or an audited equivalent, preserve full RPM metadata, and
receive its own single build, inventory, scan, and functional qualification.
It must not delete selected metadata or reuse this failed derived-image recipe.

The seven previously qualified C16 controller/runtime images remain unchanged.
Database qualification, metadata, SeaweedFS, MLflow, publication/signing, and
real Kubernetes runtime qualification remain blockers.

## Resources and validation

The pre-build gate measured 6,135,808,000 bytes available memory,
107,671,703,552 bytes free on the root filesystem, and 4,047,106,048 bytes
free in `/tmp`. The build was limited to 4 GiB and two CPUs. At closeout the
host had 7,668,441,088 bytes available memory, 107,666,726,912 bytes free on
the root filesystem, and 4,183,117,824 bytes free in `/tmp`. No C17 image,
container, or volume exists.

- Focused KFP pipeline/task and security-gate tests: 38 passed.
- Ruff and scoped MyPy: passed.
- Six-component KFP pipeline compilation: passed.
- Exact MySQL KFP render and YAML/JSON validation: passed.
- Changed-evidence Gitleaks and Git whitespace checks: passed.
- Full Python regression was not rerun because no application source or failed
  candidate Dockerfile was retained.
