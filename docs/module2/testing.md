# Module II verification evidence

Runtime evidence captured 2026-10-24:

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
