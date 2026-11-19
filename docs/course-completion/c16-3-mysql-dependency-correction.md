# C16.3 final MySQL dependency correction

**Date:** 2026-11-19

**Starting revision:** `75e07ee06977365dc07ecbacb94159c277626c9d`

**Decision:** **NO-GO — the image built, but its clean scan is not trustworthy**

No Kubernetes object, protected cluster, cloud resource, registry, or model was
changed. Functional database testing did not start because the mandatory image
security gate was not validly satisfied.

## Build and candidate

The exact four-package resolver-only check passed for embedded Python 3.13:
`certifi 2026.10.18`, `cryptography 50.0.0`, `pyOpenSSL 26.4.0`, and
`urllib3 2.8.0`; existing `cffi 2.0.0` and `pycparser 3.0` satisfied the
reported transitives. The single build retained:

- Go 1.27.4 builder
  `golang@sha256:4fa7c968ba93f1635670522dbb01a2c78150443e1385746924566079f36570ea`;
- official gosu 1.20 revision
  `29b939aa5bd4dc588af765b8248f6e39150d2565`;
- MySQL 8.4.13 base
  `mysql@sha256:a81d043930e51745522bd5c430961cf8286f0a23f0a9a2a6e0108f7ea71b0902`;
- four Oracle Linux libraries at `2.37.4-28.0.1.el9_9`.

The build completed as local image
`sha256:fcccca5dc28fe353dc30704e2311b4c4d272cf1644ea4c8f89cb325f829fc88`.
Real gosu reports `1.20 (go1.27.4 on linux/amd64; gc)`, MySQL server/client
report 8.4.13, and MySQL Shell reports 8.4.10. The Dockerfile SHA-256 was
`f33413e6ea97152f63e077f52270759dd04920faf832dd48e168b269de21473e`;
BuildKit metadata SHA-256 was
`a41003da7ecdc02b1809430deba25504640c046db1d8746e10f497117e836b02`.

## Security result and invalidating metadata defect

Trivy 0.76.2 used a freshly downloaded database and `/dev/null` as the ignore
file. The complete raw scan reported 0 HIGH and 0 CRITICAL across Oracle Linux,
embedded Python, and gosu. Its SHA-256 was
`e17c1d354463f9c03baac9d7704f2e4337783c013eb77c7f044c41714a5a3d27`;
the generated SPDX JSON SHA-256 was
`5f960d39f5c0a7bd220646e87e2daf4675e2e48e4a8ad37f4b80497d66e9eb62`.

That zero count is **not accepted**. MySQL Shell bundles `oci 2.168.2`, which
requires `cryptography <47` and `pyOpenSSL <=25.3.0`. Pip warned about both
conflicts, left both old and new `.dist-info` directories, and removed
`METADATA` from the old directories. Python package discovery selected those
malformed old directories and returned version `None`; direct inspection failed
because their `METADATA` files do not exist. Trivy consequently could not
reliably inventory the embedded packages. Accepting this result would amount to
hiding packages from the scanner, which is prohibited.

The image therefore fails qualification regardless of its raw zero count. No
additional dependency repair or build was attempted.

## Functional and remaining status

MySQL startup, database creation, authentication, least-privilege grants,
schema migration, persistence, restart, non-root process, and memory tests were
not run because they are explicitly gated on valid security qualification.

The failed task-owned candidate was removed by exact image ID after evidence
capture. The seven previously qualified C16 controller/runtime images remain
unchanged. A supported MySQL Shell/OCI dependency set, or an upstream MySQL
8.4 image that supplies one, remains the database blocker. Metadata, SeaweedFS,
MLflow, publication/signing, and real Kubernetes runtime qualification remain
later KFP blockers.

## Resources and validation

The pre-build gate measured 8,026,882,048 bytes available memory,
107,702,308,864 bytes free on the root filesystem, and 5,839,523,840 bytes
free in `/tmp`. The build was limited to 4 GiB and two CPUs. At closeout the
host had 6,174,531,584 bytes available memory, 107,656,773,632 bytes free on
the root filesystem, and 4,047,134,720 bytes free in `/tmp`.

- Focused KFP pipeline/task and security-gate tests: 38 passed.
- Ruff and scoped MyPy: passed.
- Six-component KFP pipeline compilation: passed.
- Exact MySQL KFP render and YAML/JSON validation: passed.
- Changed-evidence Gitleaks and Git whitespace checks: passed.
- Full Python regression was not rerun because no application source or failed
  candidate Dockerfile was retained.
