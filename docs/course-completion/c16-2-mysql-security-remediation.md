# C16.2 MySQL security remediation

**Date:** 2026-11-19

**Starting revision:** `5488d4422d1594361824b73553c0d21a630f4706`

**Decision:** **BLOCKED — the one authorized candidate build produced no image**

No Kubernetes object, protected cluster, cloud resource, registry, or model was
changed. No database container was started because no image reached the
security gate.

## Corrected build inputs

The prior mismatch was exact: the digest-pinned Go builder
`golang@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea`
is Debian 12 and provides `apt-get`, not Alpine's `apk`. It already contains
Git, so the corrected recipe installed no builder packages. It checked out
official gosu `1.20` revision
`29b939aa5bd4dc588af765b8248f6e39150d2565`, verified `HEAD`, downloaded the
locked Go modules, and successfully built real gosu with Go 1.27.4,
`CGO_ENABLED=0`, `-mod=readonly`, and `-trimpath`.

The runtime remained the exact KFP-selected linux/amd64 MySQL base:
`mysql@sha256:a81d043930e51745522bd5c430961cf8286f0a23f0a9a2a6e0108f7ea71b0902`.
The build upgraded only the four vulnerable Oracle Linux libraries to the
scanner-fixed `2.37.4-28.0.1.el9_9` release. The transaction log confirms four
upgrades and no additional package installation or removal.

## Python dependency blocker

The recipe pinned the scanner-fixed direct versions `certifi 2026.10.18`,
`cryptography 50.0.0`, `pyOpenSSL 26.0.0`, and `urllib3 2.8.0`. Pip rejected
the transaction before modifying the image because `pyOpenSSL 26.0.0` requires
`cryptography >=46,<47`, conflicting with the mandatory `cryptography 50.0.0`
fix.

A read-only resolver check after the stopped build established that supported
`pyOpenSSL 26.4.0` and `cryptography 50.0.0` are compatible in the embedded
Python 3.13 runtime. That correction would require another build and was not
attempted under the one-build limit.

## Qualification and functional status

The candidate image `cogniflow/mysql:8.4.13-c162` does not exist. Therefore no
image identity, Trivy result, SBOM, non-root runtime claim, MySQL startup,
authentication, schema migration, persistence, restart, or runtime-memory
result is reported. This is **BLOCKED**, not NO-GO: the build prerequisite
failed before a candidate could be scanned.

The remaining reproducible recipe correction is narrow: pair
`pyOpenSSL 26.4.0` with `cryptography 50.0.0`, retaining the already successful
OS pins and gosu build. A future explicitly authorized attempt must still build
once, run the complete unsuppressed scan, and permit functional work only at
zero HIGH and zero CRITICAL.

The seven previously qualified C16 controller/runtime images remain unchanged.
Metadata, SeaweedFS, MLflow, publication/signing, and real Kubernetes runtime
qualification remain later KFP blockers.

## Resources and validation

The pre-build gate measured 8,022,806,528 bytes available memory and
110,200,135,680 bytes free on the root filesystem. At closeout the host had
8,305,831,936 bytes available memory, 107,706,925,056 bytes free on the root
filesystem, and 5,839,552,512 bytes free in `/tmp`. The build was limited to
4 GiB and two CPUs. No task-owned image, container, or volume remained.

- Focused KFP pipeline/task and security-gate tests: 38 passed.
- Ruff and scoped MyPy: passed.
- Six-component KFP pipeline compilation: passed.
- Exact MySQL KFP render and YAML/JSON validation: passed.
- Changed-evidence Gitleaks and Git whitespace checks: passed.
- Full Python regression was not rerun because no application source or usable
  build source was retained.
