# C23 KFP training-component qualification

**Date:** 2026-11-19  
**Source revision:** `acc3bef1abc8c985867ee7dc36b154dd07a54c6d`  
**Decision:** **PASS_LOCAL — Kubernetes execution remains blocked**

The previous six-stage component image had 60 HIGH findings. The replacement
uses only the existing task implementation and its hash-locked runtime
dependencies on the same qualified Wolfi base used by the metadata services.
It does not add a second training path.

## Exact image and security evidence

- Local image/index digest:
  `sha256:e296269ccaa235661a1102c49bc98754f5a3d07e80c8c59e5e78d83a8cc2d1f9`
- Runtime manifest: `sha256:90ecb73bfe8a28fdffbc3d4a7df39646589a12f4c4de5622b7224224fe41adee`
- Build attestation manifest:
  `sha256:b4231572af2b08faecc6af9cac29e697df8c815daf3bde2441c36a9625f0805d`
- Runtime identity: UID/GID `65532`; read-only and network-disabled checks passed.
- Trivy 0.76.2 database updated `2026-11-19T19:04:59Z`.
- Complete inventory: 34 Wolfi packages and 89 Python distributions.
- Findings: **0 HIGH, 0 CRITICAL**.
- Raw scan SHA-256:
  `5017932de031fa1870b7a01092c3dfd96eb3672850168f4de481a1a6d1ad8b86`.
- SPDX SHA-256:
  `d36e0e8820e0e195188b7abffdae65a97ce84e1fe3a5442f8a0f2a0c2e615efe`.

No registry publication, remote signature or remote attestation is claimed.
The first rejected build embedded the wrong expanded short SHA and is excluded
from all configuration and evidence.

## Isolated functional acceptance

All six production commands ran in separate disposable, network-disabled
containers against the deterministic 180-row fixture:

1. input validation;
2. group-disjoint dataset preparation (108 train, 36 validation, 36 test);
3. Random Forest, Logistic Regression and majority-baseline training;
4. predeclared selection and held-out evaluation;
5. candidate-only registration in a task-owned local MLflow SQLite store; and
6. provenance reconciliation.

Dataset SHA-256 was
`6679e9edb87451ee968e21c0aef5280226b2cf609554e048ec365378c3aca80f`;
split SHA-256 was
`1b3ec0fb93c8b829af83560b2b4de8766178182d15497d5ad8a514ac962098b9`.
The deterministic rule selected Logistic Regression. Validation and test
accuracy/macro-F1 were 1.0/1.0 on the synthetic proxy fixture. These results do
not establish clinical validity or a real KFP run.

The task-owned registration was candidate version 1 with run
`b8b7a0b6c2394774aa1bac70ab66925a`. Its pipeline ID was deliberately
`not-a-kfp-run`; it is not runtime evidence and is not approved.

The compiled six-component specification now uses the qualified local digest
for every executor. Kubernetes execution still requires byte-identical remote
publication, signatures/attestations, an authorized isolated target and real
KFP-generated run identity.

## Regression

- Full Python suite: 687 passed, 2 skipped; 87.00% coverage (81% gate).
- Ruff and scoped MyPy: passed.
- Helm lint/render and Module II Compose validation: passed.
- Terraform format and provider-backed validation: passed after backend-disabled
  initialization with the lockfile-pinned, HashiCorp-signed provider; no plan or
  cloud operation ran.
- Checksum-verified Gitleaks 8.30.1 scanned a tracked-tree snapshot plus these
  changes: zero findings. Redacted report SHA-256 is
  `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`.
