# Module II M2-S1E — Spark deferral closeout

**Decision: DEFER_SPARK_ENFORCED (2026-11-21).** This closes the current security investigation, not the Spark or Module II functional qualification.

## A. Evidence verification

Reviewed M2-S1B, M2-S1C, and M2-S1D. The M2-S1D manifest `build/security-scans/spark4-security-candidate-2026-11-21/evidence-checksums.sha256` verified all 383 retained files. Its manifest SHA-256 is `5df8c5226914aefd347a695fd1b8383473c0f4ee95bb2a0ec5e06b374ed17038`. The M2-S1B report references retained categorized vulnerabilities and convergence evidence; earlier scan totals are historical results, not fresh M2-S1E scans. M2-S1D records incomplete Analytics Accelerator and WildFly signature provenance, incomplete Delta transitive and Python language package coverage, and unresolved functional compatibility. No image was scanned or built here.

## B. Final subsystem qualification status

| Subsystem | Status and exact boundary |
| --- | --- |
| Airflow | PASS, local orchestration against mocks only |
| Trino/dbt | PASS, independent local analytics only |
| Spark | BLOCKED, image and S3A security gates failed; real execution not qualified |
| End-to-end Module II | UNVERIFIED, real Spark integration not executed |
| Cloud/Kubernetes | NOT QUALIFIED |
| Production | NOT READY |

Observed security results remain Spark 3.5.5: 152 HIGH/5 CRITICAL; Spark 3.5.9: 525 HIGH/22 CRITICAL; Spark 4.2.1: 579 HIGH/24 CRITICAL; Hadoop 3.5.0 S3A closure: 15 HIGH/1 CRITICAL. The M2-S1D image scan and the standalone closure scan are distinct inventories and must not be added as one image total.

## C. Runtime and CI safeguards

Compose puts the configured Spark service behind the `batch` profile, uses a non-root UID, internal networks, read-only mounts, and requires a token. The Ivy checksum gate confirms artifact identity, not vulnerability clearance. These controls do not prevent an operator with a valid token from using `docker compose --profile batch up` and `/run` to launch blocked Spark. The separate rehearsal script has SEC-022 identity and image security gates, but those do not cover direct Compose invocation. No CI workflow was found that starts Spark as an accepted qualification; existing acceptance reporting labels Spark blocked.

`jobs/internal_job_runner.py` now fails startup when `JOB_KIND=spark` and rejects direct `run_job("spark", ...)` calls before subprocess execution. Its dbt path remains unchanged. A user with direct Docker or shell control can bypass an application guard; therefore this enforces the supported runner workflow, not an operating system restriction. The production security policy and SEC-022 were not changed.

## D. Safeguard tests and regressions

- Focused runner and rehearsal tests: 19 passed.
- Ruff on changed Python files: passed.
- Compose configuration validation: passed.
- `git diff --check`: passed.
- Scoped MyPy: six errors in imported `jobs/bronze_to_silver.py` due to unavailable boto3/botocore, Delta, PySpark and project package typing; no error was reported in the changed guard. This is not a MyPy pass.
- Full regression suite omitted because the change is confined to Spark runner deferral.

## E. Reopening criteria

Resume only after a concrete upstream or vendor supported remediation exists; verify exact candidate image provenance; scan the full image and all required external dependencies to zero HIGH and zero CRITICAL; resolve converged and shaded dependency concerns; and obtain approval for a separate security qualification. Security clearance must precede real Spark execution. Functional integration requires its own subsequent qualification and is never inferred from a clean scan.

## F. Preserved artifacts

Raw scans, package inventories, artifact hashes, manifests, signature results, and static analysis remain in ignored `build/security-scans/` directories. All existing Docker containers, volumes, images, networks, and unrelated working tree changes were preserved. This milestone created no Docker resource.

## G. Remaining risks

An operator can directly run the blocked image outside the supported runner. The existing Compose `batch` profile is available for future qualification and does not itself enforce the security decision. Evidence gaps from M2-S1D remain. Spark, full integration, cloud and production remain unqualified.

## H. Files changed

- `jobs/internal_job_runner.py`: fail closed on Spark runner startup and submit.
- `src/tests/test_internal_job_runner.py`: focused startup and direct invocation regression.
- This report.

## I. Final decision

**DEFER_SPARK_ENFORCED** for CogniFlow's supported authenticated runner path. The deferral remains in effect until the reopening criteria are satisfied.
