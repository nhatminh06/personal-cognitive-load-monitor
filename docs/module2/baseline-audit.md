# Module II baseline audit

Captured 2026-10-23 on `feature/cogniflow-module2-data-engineering` at Module I commit `89b91f67dec6e81aee53e59854704050f35d4afc`.

## Evidence

- Working tree was clean and the branch pointed exactly at the Module I baseline.
- Module I regression: 42 tests passed; 88.41% total coverage with the 81% gate.
- Graphify: 281 nodes, 419 edges, 24 communities. HCL parsing and semantic labels remain unavailable because optional dependencies/Gemini credentials are absent.
- Host: 15 GiB RAM, 3.6 GiB available, 13 GiB swap used; 263 GiB repository filesystem space available; `/tmp` only 1.3 GiB free.
- Docker Engine 29.9.1 is available. Java 21 exists on the host, but Spark/Flink/Trino/Airflow/dbt CLIs are not installed; their pinned containers isolate supported Java/Python runtimes.
- Only the existing observability Compose file existed. No Kafka, MinIO, Spark, Delta, Trino, dbt, Airflow, Flink, or Redis implementation existed at baseline.
- UI/UX Pro Max is not installed. Ponytail full and Graphify 0.9.92 are available.

## Reusable Module I assets

- `PredictionRequest` supplies the authoritative measurement ranges.
- `FEATURE_NAMES` and `feature_vector` supply exact ordering and ratio semantics.
- JSON logging, Prometheus middleware, trace configuration and the dependency-free UI can be extended.
- Docker, Makefile, test patterns, DVC lineage and documentation conventions remain intact.

## Risks and decisions

- Kafka must not become a `/predict` dependency; `/events` is additive and fail-closed.
- External engines cannot import arbitrary application Python consistently, so checked-in parity vectors will test Spark/Flink transformations against Module I.
- Trino Delta requires a metastore; begin with its lightweight file metastore for local tests and document the production HMS requirement.
- End-to-end delivery is at least once. Unique event IDs and deterministic storage/merge keys provide idempotency, not an unsupported exactly-once claim.
- Full simultaneous runtime, 100GB processing and paid-cloud evidence are unavailable at this baseline.
