# C20 MLMD, metadata writer and MLflow integration

**Date:** 2026-11-19

**Starting revision:** `b552cc1f8dc22988f68a4ca6b379a4851c47ecd8`

**Decision:** **PARTIAL**

## Qualified and executed

A pinned Wolfi/Python 3.13 build produced MLflow 3.17.2 image
`sha256:de0b5f8bbd26bfea3693700b90a9602cfb5620cb64887a908da60bad4ba863b5`.
The runtime is non-root (65532:65532), has 34 OS packages and 92 Python
distributions, and uses a fully hashed lock. Trivy 0.76.2 scanned both Wolfi and
Python inventories with databases updated on 2026-11-19 and reported 0 HIGH and
0 CRITICAL. The unsuppressed scan SHA-256 is
`22013078449571e9a4eeaf81fd027b26319155d81a15ad7a7b458d5c29677335`;
the independent SPDX JSON SHA-256 is
`67976750e7a512182d2d4106f2992115044804a34b5cd466a6b1b0ac8ae28c49`.
BuildKit emitted a local provenance attestation manifest, but no remote
signature or SLSA attestation exists.

The bounded integration used the retained qualified C18 MySQL and C19
SeaweedFS images. MLflow created its authentic MySQL schema, experiment 1 and
run `15093afd53674e409be8cb83fa188f6a`, logged the synthetic six-feature
fixture, parameter, metric and scikit-learn model, and registered unapproved
candidate `cogniflow-c20-synthetic/1`. Direct S3 readback matched fixture
SHA-256 `7ecfa75ed0c1c3d4a8d121ccab9993664a2ccbb1f0c5289831f0999a62d66b18`.
The independently retrieved model package tree SHA-256 is
`604819aba0e5eaa4ec0728e06a4204db83bd259cd68a099053cd1db702ed582b`.
Wrong S3 credentials and a nonexistent artifact were rejected. MySQL,
SeaweedFS and MLflow were restarted; the same run, model version and bytes were
retrieved afterward. Only C20-labeled containers, volumes and network were
removed.

The isolated MLflow manifest now uses the exact local OCI identity, MySQL via a
Secret, SeaweedFS S3 artifacts, UID/GID 65532, a read-only root filesystem and
bounded ephemeral `/tmp`. `imagePullPolicy: Never` intentionally makes this a
local-only overlay: a published, signed remote digest must replace it before an
authorized Kubernetes run.

## Blocked paths

The one MLMD supported-base build stopped before image export because Ubuntu
24.04 already owns UID 1000. The one metadata-writer pinned-source build
produced no image. Per the bounded-remediation rule neither path was retried,
and their failed recipes were not committed. Therefore there is no new MLMD
scan, authentic MLMD migration/write/read evidence, or metadata publication
evidence. Metadata-writer behavior also needs an authorized Kubernetes API and
real workflow context; it was not counterfeited locally.

KFP 2.18.1/Argo 4.1.6 controller identities, metadata Envoy, init helper,
MySQL and SeaweedFS remain as recorded by C16-C19. The complete deployment is
not runnable until MLMD and metadata writer qualify, every local image is
published and signed under a remote immutable digest, Secrets and service
accounts are provisioned, and an isolated owner-authorized Kubernetes runtime
passes the 12 GiB gate. No KFP run ID or Kubernetes readiness claim was made.

## Resources and validation

Available memory was 7,589,289,984 bytes before integration and 7,498,706,944
after cleanup. Maximum observed container use was 507.7 MiB MySQL, 175.1 MiB
SeaweedFS and 1.474 GiB MLflow. The disposable volumes held 227,763,186 and
34,446 bytes respectively before removal; both protected kind clusters were
untouched.

- Focused tests: 30 passed, one warning.
- Full regression: 679 passed, 5 skipped, 5 warnings; 87.00% coverage.
- Ruff, scoped MyPy, Compose validation, Helm lint/render, YAML structure and
  Git whitespace checks passed.
- KFP compilation remains covered by the focused suite; no pipeline ran.
- Gitleaks is not installed, so a fresh secret scan is BLOCKED rather than
  claimed as passed.

The machine-readable [assessment](c20-evidence/assessment.json) binds the
identities, digests, statuses and measurements.
