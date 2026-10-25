# Dependency audit

Commands used:

```text
uvx --python 3.11 --from bandit==1.8.6 bandit -r src jobs scripts dags -x src/tests -f json
uv export --frozen --all-extras --no-hashes
uvx --python 3.11 --from pip-audit==2.9.0 pip-audit -r <temporary-export>
uv lock --upgrade
```

Bandit 1.8.6 scanned 1,563 lines with no scan errors under Python 3.11: 0 High, 3 Medium and 7 Low alerts. The Medium alerts were a fixed container-local `/tmp/dbt-*` path (not a host temporary-file creation primitive) and a `requests.post` call that already supplies a configurable timeout. Low alerts were deterministic non-cryptographic generators and assertions in a verification-only Spark job.

The initial pip-audit run found advisories in the lockfile, including aiohttp, Starlette, cryptography, MLflow, GitPython, Jupyter, Pillow, Tornado and urllib3. `uv lock --upgrade` selected fixed releases, the obsolete FastAPI ceiling was relaxed so a fixed Starlette could resolve, and pandas was constrained below 3 for Evidently compatibility. One advisory remains: PYSEC-2026-2447 in diskcache 5.6.3 has no published fix. It requires attacker write access to the DVC development cache before a trusted process reads the pickle; diskcache is not in the runtime API image. Treat shared/untrusted DVC cache directories as unsafe and remove/upgrade diskcache when a fix exists. Advisory results are point-in-time and require recurring CI scans.

Final gate update: pip-audit 2.9.0 inspected 297 locked dependencies and again found only `diskcache 5.6.3` / PYSEC-2026-2447 with no fixed release. Trivy 0.76.1 found no High/Critical vulnerability in tracked Python dependency manifests.

Java Maven dependencies were compiled/tested through the pinned Maven container because the host has no Maven executable. Four Flink JUnit tests passed. Trivy directly scanned the packaged Java dependencies: Flink has no High/Critical result, but the current Spark 3.5.5 image scan has 126 fixable High/Critical occurrences (107 distinct IDs), including five Critical occurrences. This is SEC-022 and blocks release; non-root execution and the authenticated fixed-command runner reduce exposure but are not remediation.

Complete Trivy 0.76.1 candidate scans used the current vulnerability database and exact image digests. Spark 3.5.9 contained 78 Java High/Critical occurrences and Spark 4.1.3 contained 79, in addition to 641 Ubuntu occurrences each. Both candidates were rejected rather than changing Maven coordinates or deleting runtime jars without compatibility evidence.

The final normal-resolution dbt combination is `dbt-core 1.11.14`, `dbt-trino 1.10.6`, and `sqlparse 0.6.0`. `pip check`, parse, compile, two builds, and eight explicit dbt tests passed. The exact dbt image has zero fixable High/Critical findings.
