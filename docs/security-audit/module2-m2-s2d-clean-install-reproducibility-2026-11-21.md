# M2-S2D — Clean install independent regression qualification

**Decision: PASS_CLEAN_INSTALL (2026-11-21).** A fresh Python 3.11 virtual environment from the frozen lock passed the independent offline checks. This is not a new runtime image security qualification.

## A. Repository and environment baseline

Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`. Existing modifications to `Makefile`, runner and tests, plus untracked audit reports and raw evidence, were preserved. Read `AGENTS.md`, M2-S2A/B/C, `pyproject.toml`, `uv.lock`, and the selected tests. Host preflight: 8.5 GiB available RAM, 10 GiB free swap, 7.6 GiB free `/tmp`. Python `3.11.17`; uv `0.13.0`.

Task ownership was limited to `/tmp/cogniflow-m2s2d-JOylK3/` (source, `venv`, empty-start cache, and evidence subdirectories) and ignored `build/module2-clean-install-qualification-2026-11-21/installed-packages.txt`. The existing repository `.venv`, caches, Docker resources, and qualification evidence were not modified. The temporary directory is to be removed after this report.

## B. Dependency selection and integrity

`uv.lock` SHA-256: `726346e01eb782a7fa75ceae7b7ff055a5f178457d000c962eaceb210386d920`. The lock uses `https://pypi.org/simple` and hashed distributions from `https://files.pythonhosted.org`; no custom index or direct Git URL was selected. `uv export --frozen --extra dev --no-default-groups --no-emit-project` showed 302 exported requirements across platform markers and no PySpark, Delta Spark, or Hadoop requirement. The actual Python 3.11 installation selected 290 distributions, with no blocked Spark package. The selection is broader than the five test files alone because the project base dependencies and `dev` extra are the smallest existing locked selection that includes all required test, lint, and application imports. No lockfile, declaration, or package version was changed.

## C. Fresh installation

Created a new virtual environment with `UV_CACHE_DIR=/tmp/cogniflow-m2s2d-JOylK3/cache uv venv --python python3.11 /tmp/cogniflow-m2s2d-JOylK3/venv`. From the source copy, installed using `UV_CACHE_DIR=/tmp/cogniflow-m2s2d-JOylK3/cache UV_PROJECT_ENVIRONMENT=/tmp/cogniflow-m2s2d-JOylK3/venv uv sync --frozen --extra dev --no-default-groups --no-install-project --python /tmp/cogniflow-m2s2d-JOylK3/venv/bin/python --no-progress`. The initial sandboxed attempt could not resolve `files.pythonhosted.org`; the same command succeeded with network approval, downloading/building 290 packages into the task cache and installing 290. The project itself was not installed: tests imported repository code from the source copy. A subsequent `uv sync` with identical selection and `--offline` checked 290 packages without changes.

Installed inventory SHA-256: `0622c97ba90fa5d6e48405811a6cc7679369891b579435974c463c2e9a602650`; full version list retained under ignored `build/module2-clean-install-qualification-2026-11-21/`. Selected versions include pytest 9.1.1, MyPy 2.4.0, Ruff 0.15.17, PyArrow 25.0.1, PyYAML 6.0.3, Pydantic 2.14.1, FastAPI 0.162.0, and HTTPX 0.28.1. `uv pip check --python /tmp/cogniflow-m2s2d-JOylK3/venv/bin/python` reported all 290 installed packages compatible. The new environment had no pip module, so the equivalent uv check was used. uv verified locked wheel hashes during fresh downloads; no separate wheel signature verification or vulnerability scan was performed.

## D. Source only isolation

Built the temporary source from `git archive HEAD` and overlaid the intended local edits to `Makefile`, `jobs/internal_job_runner.py`, the Airflow and runner tests, the untracked analytics test, and the tracked intended fixture. The copy excluded ignored `build/` evidence, existing `.venv`, caches, secrets, and machine artifacts. Fixture SHA-256 in the copy was `85aa6318227dcf7ce01d3cb0218114bc761d66779957795fbf5b86893d074961`; the ignored analytics evidence directory was absent. A temporary `.venv/bin/pytest` symlink inside the copy pointed only to the new environment so the existing Make target could run unchanged. No repository source or existing environment was altered.

## E. Offline regression results

In the isolated source copy, `make module2-independent-regression` passed **29 tests** in 0.11 seconds. The same explicit five-file selection using the new interpreter passed 29 tests in 0.27 seconds. These include the Spark startup/submission/validation fail closed guards and the three-row, 135-focus-minute synthetic oracle. No Spark executable, container, cloud service, credential, or ignored evidence file was used.

## F. MyPy and Ruff

`/tmp/cogniflow-m2s2d-JOylK3/venv/bin/mypy jobs/internal_job_runner.py` passed: `Success: no issues found in 1 source file`. Ruff from the same environment on the changed runner and test files passed. The original settings were retained.

## G. Compose and diff checks

`docker compose -f infra/module2/docker-compose.yml config --quiet` passed in the source copy; this parsed configuration only and started no container. `git diff --check` passed in the actual repository. The source copy is an archive without `.git`, so a `git diff --check` invocation there returned `Not a git repository`; it was not counted as a pass. The report's own whitespace was checked separately.

## H. Evidence and cleanup

The installed package inventory is retained in ignored local evidence. All previous audit artifacts and Docker resources remain untouched. The task owned approximately 1.3 GiB under `/tmp` during verification; it is removed after final checks. No second empty-cache install was needed because the first successful install explicitly downloaded into an empty task cache and the offline resync confirmed the frozen selection.

## I. Remaining limitations

This qualifies a clean Python 3.11 installation for the independent offline regression only. It does not rescan installed Python packages for vulnerabilities, repeat live Airflow or Trino/dbt qualification, or establish Spark security or full Module II functionality. The fresh install pulled the project's broad base and `dev` extra; a narrower dedicated lock is not present and was not invented.

## J. Final decision

**PASS_CLEAN_INSTALL.** The frozen dependency selection, 29 offline tests, original scoped MyPy, Ruff, Compose parsing, and repository diff check passed without blocked runtime activity. Airflow mock orchestration and Trino/dbt retain only their earlier independent PASS boundaries. Spark remains BLOCKED with DEFER_SPARK_ENFORCED, full Module II remains UNVERIFIED, cloud/Kubernetes NOT QUALIFIED, and production NOT READY.
