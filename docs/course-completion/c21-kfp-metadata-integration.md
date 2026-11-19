# C21 KFP metadata integration

**Date:** 2026-11-19

**Starting revision:** `aced4d15797f34ac5db8507590261ffbcfd738f0`

**Decision:** **PARTIAL — authentic MLMD integration passed; metadata writer remains blocked**

## MLMD image qualification

The C20 failure was an account collision: Ubuntu 24.04 already owns UID 1000.
The corrected build assigns the dedicated non-privileged UID/GID 10001 and
preserves the upstream MLMD server byte-for-byte. Both source and rebuilt
binary have SHA-256
`d170da72e14dfc4726f7f9cfbe48d57cfa4c0dedbe42a8224880be5d879aa584`.

The exact new local image is
`sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876`.
It runs as 10001:10001 on supported Ubuntu 24.04. Trivy 0.76.2 inventoried 95
dpkg packages and reported 0 HIGH and 0 CRITICAL findings with no suppressions.
The scan SHA-256 is
`30ba16ae7395086197fefbf6384368d002a9ce0a444767f28d8eb7daca8385fc`;
the SPDX SHA-256 is
`330f6bb0e8b35c7cd82217688a707d65119fdbf391f2971b3a851ab5d60812e6`.
The BuildKit attestation is local only; no remote signature or SLSA claim was
made.

## Authentic MySQL and MLMD execution

The qualified C18 MySQL image and new MLMD image ran in an isolated C21
network. MLMD 1.14 cannot authenticate with MySQL 8.4's default
`caching_sha2_password`; this is the same compatibility constraint encoded by
KFP 2.18.1's upstream MySQL manifest. The test enabled MySQL's built-in
`mysql_native_password` plugin for a dedicated `mlmd` account limited to
`metadb`; root remained on `caching_sha2_password`. The overlay applies the
same policy through a separately provisioned `cogniflow-mysql` Secret.

The real MLMD server migrated `metadb` to schema version 10. A real
`ml_metadata` 1.21 gRPC client created an artifact type, execution type,
context type, artifact, execution, context, output event, attribution and
association. API readback returned artifact, execution and context IDs 1;
independent MySQL queries confirmed one artifact, execution, context and event.
After restarting both services, the same records and schema version were read
again. A wrong database password exited nonzero (139) with
`mysql_real_connect failed`. Only C21-owned resources were removed.

Maximum observed memory was 445.8 MiB for MySQL and 19.08 MiB for MLMD. The
disposable MySQL volume held 220,610,285 bytes before cleanup.

## Metadata writer blocker

The C20 archive mismatch was confirmed: its expected `49da…` checksum did not
match the authentic KFP commit archive. KFP 2.18.1 source commit
`7dd28116ad652bfb7b6c282e7920be84e6a7634a` was independently retrieved as
archive SHA-256
`4b50a172728854115776532673e0df6d98679fb8303a806d901bb7825e359e55`,
and its writer source matched the retained verified files.

The single C21 corrected build stopped before image creation because the
pinned Wolfi builder does not contain `wget`. C21's bounded-remediation rule
prohibits another build, so there is no new writer image, scan or startup
claim. Actual writer publication additionally requires an authorized
Kubernetes API and Argo workflow objects. No workflow context was fabricated.

## Headless KFP overlay and acceptance boundary

The isolated overlay now pins the qualified MLMD, MySQL, MLflow, SeaweedFS,
metadata Envoy, KFP API/persistence/scheduler/driver/launcher and Argo
controller/executor identities. It removes optional cache/UI/viewer resources
because all six pipeline components disable caching. MySQL and MLMD use the
external `cogniflow-mysql` Secret; the upstream empty Secret is deleted. The
MySQL security context uses its packaged UID/GID 27, and MLMD uses 10001.

Rendering against C19's retained exact KFP 2.18.1/Argo 4.1.6 base produced 73
documents with SHA-256
`40b13f124fdc6aafb2d73fbcf4f59f14de3885cac584aeee01f6230a2a4020c5`.
All 73 documents passed the retained Kubernetes 1.34 structural OpenAPI
schemas. Of 16 container image uses, metadata writer is the only remaining
mutable/unqualified image. A direct remote render was also attempted but the
pinned Argo Git fetch exceeded Kustomize's 27-second timeout; no cluster was
contacted.

The six-component pipeline compiled with SHA-256
`82cfee1f552b9be5e4b9bee0f01401773afe8689f68e3642d90997442c1aee74`.
There is no KFP run ID, controller readiness evidence or writer publication,
so C10/C11 runtime checks remain BLOCKED. C20's MLflow run
`15093afd53674e409be8cb83fa188f6a`, unapproved model version 1 and artifact
checksum remain local component evidence only.

## Validation

- Focused metadata/KFP/acceptance tests: 35 passed, one warning.
- Full regression: 684 passed, 5 skipped, 5 warnings; 86.95% coverage.
- Ruff, scoped MyPy, Helm lint/render, Compose validation, KFP compilation,
  Kustomize rendering, OpenAPI validation and Git whitespace checks passed.
- Gitleaks and ShellCheck are not installed, so both are BLOCKED rather than
  claimed as passed.

The machine-readable [assessment](c21-evidence/assessment.json) records exact
identities, results and boundaries.
