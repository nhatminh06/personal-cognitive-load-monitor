# C16.1 KFP database qualification

**Date:** 2026-11-19

**Starting revision:** `4fb770568c01c48ff1d550413c9124adc3c5f5cf`

**Decision:** **BLOCKED — the one bounded remediation attempt produced no image**

No Kubernetes object, protected cluster, cloud resource, registry, or model was
changed. No database container was started because the security gate did not
pass.

## Supported database selection

The exact KFP `2.18.1` `platform-agnostic` kustomization selects MySQL. Its
render has 78 resources and SHA-256
`1e70dd98380ed9e034505961474cc040dbef054c213ce1388d34af323d431e0e`.
The shared install config selects `dbType=mysql`, `mysql:3306`, and the
`mlpipeline`, `cachedb`, and `metadb` databases. The API server consumes the
MySQL settings, while MLMD connects to `metadb` and starts with
`--enable_database_upgrade=true`. The persistence agent and scheduler call the
API and do not select an independent database backend.

MySQL is the KFP 2.18 production backend. The PostgreSQL overlay is a
development/evaluation option with an MLMD concurrency limitation; its rendered
config also retains the base `dbType=mysql` while adding `DBDriverName=pgx`, so
it is not a safer production default. The C16 PostgreSQL selection is therefore
superseded for database architecture, without changing production manifests.
The C14 isolated test used the same MySQL 8.4 family and observed successful API
`AutoMigrate`, so its initialization path agrees with this architecture.

## Security qualification

The exact local linux/amd64 KFP manifest image is
`mysql:8.4@sha256:a81d043930e51745522bd5c430961cf8286f0a23f0a9a2a6e0108f7ea71b0902`.
Trivy 0.76.2 performed a complete unsuppressed OS and language scan. The scan
SHA-256 is `45d42ac44dc38c4f04b020b9005f37196564cc805de5f2999a8f4e761998e8e0`.

| Finding class | HIGH | CRITICAL |
|---|---:|---:|
| Oracle Linux 9.8 packages | 8 | 0 |
| MySQL Shell embedded Python | 8 | 1 |
| `/usr/local/bin/gosu` embedded Go | 26 | 1 |
| **Total** | **42** | **2** |

The image fails the mandatory zero-HIGH/zero-CRITICAL gate. Consequently,
startup, authentication, schema creation, persistence, restart, process UID,
and memory tests were correctly not run.

## One remediation attempt

Official gosu releases use tags `1.19` and `1.20`, not a Go module version such
as `v1.19`. `git ls-remote` resolved `1.20` to verified revision
`29b939aa5bd4dc588af765b8248f6e39150d2565`. The attempted derived build was
designed to keep the official MySQL entrypoint, update Oracle Linux and embedded
MySQL Shell Python packages, and replace gosu with that source built by Go
1.27.4.

The attempt stopped before image creation: the selected, digest-pinned Go
1.27.4 builder was Debian-based but the recipe invoked `apk`. Per the explicit
one-attempt bound, it was not retried. The unusable Dockerfile was not retained,
no false image identity or qualification evidence was recorded, and no runtime
test was allowed to bypass the failed scan.

## Resources, inventory, and remaining blockers

Before qualification, the host had 7.6 GiB available memory and 103 GiB free
disk. At closeout it had 8,265,003,008 bytes available memory,
5,846,962,176 bytes free in `/tmp`, and 110,201,729,024 bytes free on the root
filesystem. No task container or volume required cleanup.

The seven C16-qualified local controller/runtime images remain unchanged. The
database inventory now correctly selects MySQL but has no qualified local image.
The next authorized attempt must correct the builder package-manager mismatch,
retain and test real gosu privilege dropping, update all three vulnerability
classes, and then pass the complete scan before isolated database integration.
Metadata, SeaweedFS, MLflow, publication/signing, and real Kubernetes runtime
qualification remain later blockers. This result does not claim full KFP
runtime readiness.

## Validation

- Focused KFP pipeline/task and security-gate tests: 38 passed.
- Full regression: 675 passed, 5 skipped, 5 warnings; 87% coverage.
- Ruff and scoped MyPy: passed.
- Six-component KFP pipeline compilation: passed with immutable component image.
- MySQL and PostgreSQL kustomize renders and YAML parsing: passed.
- JSON and Git whitespace validation: passed.
- Gitleaks on the changed evidence: no leaks. The repository-history scan still
  reports three pre-existing `curl-auth-user` findings in
  `docs/cloud-deployment.md` from commit `2a2f16b`; this task did not alter or
  suppress them.
