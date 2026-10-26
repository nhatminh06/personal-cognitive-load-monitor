# Module II verification evidence

Runtime evidence captured 2026-10-24 and revalidated where stated on 2026-10-25:

- Kafka: authenticated API accepted and broker acknowledged real events.
- Bronze: one Kafka event stored/read with topic, partition, offset and checksum.
- Silver: one row; Delta history `0 WRITE`, `1 MERGE`; rerun remained one row.
- Trino: queried the true Delta table and returned ratios `0.75/0.25`.
- dbt: two consecutive runs, each `PASS=15`, six incremental Gold tables.
- Airflow: six-task DAG test completed with state `success`.
- Flink: genuine job ID `004931d4451a5e27e6ae8b6cdf82ba18` reached `RUNNING`.
- Redis/Kafka/API: streaming event returned `0.8/0.2`, timestamp and Flink provenance through all three.

Final local regression: 59 Pytest tests passed; combined Module I/II Python coverage was 87.79%; Ruff passed; MyPy passed for both packages with third-party missing imports ignored; DVC reported all three stages unchanged/cached; all four notebooks executed; Compose validated; and both demo-rule and local-model Docker smoke tests returned `is_fallback=false`. The deterministic tiny generator wrote 10 records / 4,989 bytes with SHA-256 `aa93f7a0a8a1ce51e1a9d3bd4a8a5772a283f86aa985cb8aaf30c2269188a2c2`.

Graphify updated structurally from 281/419/24 to 497 nodes/838 edges/35 communities. Semantic, SQL, and HCL extraction were unavailable. The initial notebook run failed only because the restricted sandbox prohibited local kernel sockets; the approved local rerun executed all four successfully.

Final-hardening evidence on 2026-10-24:

- Python: 64 tests passed; combined coverage 89.74%; Ruff passed.
- Java: the Flink image build ran Maven/JUnit successfully against the shared JSON fixture.
- Spark 3.5.5 / Java 11: `jobs/verify_feature_parity.py` ran the same three fixtures through the real Spark expressions and returned `{"engine":"spark","cases":3,"status":"passed"}`. An initial Python 3.8 incompatibility in the test runner (`zip(strict=...)`) failed visibly and was removed before the passing rerun.
- Flink: job `d092287758b0063f68c6bc46ca122256` ran six operators. The deterministic 10-second window matched the fixture oracle exactly (11 unique events, focus 693, distraction 512, ratios `0.575103734439834/0.42489626556016596`).
- Recovery: after TaskManager restart, the job returned `RUNNING`; checkpoint API reported `restored=1`, eight completed and zero failed checkpoints.
- Redis: the stale timestamp Lua test returned `0` and preserved the newer `15:00:09Z` value.
- Observability: Prometheus reported `up=1` for API, Flink JobManager and TaskManager; Grafana API returned dashboard UID `cogniflow-module2`.
- Resource cleanup: observability was removed and Kafka/Flink/Redis stopped without deleting named volumes. Available host memory after shutdown was 6.6 GiB.
- Graphify 0.9.92 code-only update: 542 nodes, 944 edges, 31 communities. Semantic extraction was unavailable without an approved LLM key; SQL/HCL parsers were not installed, and `serviceaccount.yaml` was conservatively skipped as potentially sensitive.

Batch/Airflow Prometheus exporters and a fresh rerun of every heavyweight batch service remain explicit gaps; earlier real batch evidence above is retained and not relabeled as a new run.

Security-gate rerun on 2026-10-25:

- Airflow 3.3.2 completed all six tasks in 163.24 seconds with LocalExecutor, UID 50000, no Docker socket, and authenticated fixed-command Spark/dbt runners.
- The preserved MinIO volume contained 91 objects / 105,683 bytes. Every object SHA-256 matched after copying to a new SeaweedFS 4.50 volume; the source volume was not altered. boto3 read/write, S3A, Delta MERGE/reopen, Trino, dbt, and replay tests passed.
- dbt-core 1.11.14, dbt-trino 1.10.6, and sqlparse 0.6.0 passed `pip check`, parse, compile, two builds (`PASS=15` each), and eight explicit tests.
- Python: 73 passed with 88.67% coverage; Ruff and MyPy passed. Flink: four JUnit tests passed. DVC and all four notebooks executed.
- At that security gate, Airflow, SeaweedFS, dbt, API, and Flink images had zero fixable High/Critical findings. Spark 3.5.5 had 126 High/Critical occurrences: 122 with reported fixes, 4 without, 107 distinct IDs and 5 Critical; the later owner decision accepts rather than remediates them.
- Later exact-digest scans rejected Spark 3.5.9 (719 occurrences: 181 with fixes and 538 without; 699 distinct, 29 Critical) and Spark 4.1.3 (720: 184 with fixes and 536 without; 685 distinct, 27 Critical). No unverified candidate replaced Spark 3.5.5.
- The isolated SeaweedFS topology preserved authenticated S3 access and bucket inventory (Bronze 1 object, lakehouse 141 objects) while a default-network client could not resolve `seaweedfs:9333`.

SEC-022 exception validation on 2026-10-25 used only new disposable volumes. Six approved Ivy JARs matched the manifest, and the cache remained read-only. Spark ran without runtime Ivy resolution, read two deterministic Bronze records through S3A, wrote/reopened Delta, and replayed twice without increasing the row count; Trino returned two rows with Delta history `WRITE`, `MERGE`, `MERGE`. dbt passed 15/15 and the real six-task Airflow DAG succeeded; wrong/missing tokens, missing/tampered JARs, public internet access and unrelated-network access all failed closed. The final Python regression was 76 passed at 88.67% coverage; Ruff, MyPy, Compose, Helm and Gitleaks passed, and DVC reported the pipeline up to date. Temporary services and networks were stopped without deleting named volumes. This validates compensating controls only; SEC-022 remains unpatched and is accepted for isolated local development only through 2027-01-23.
