# Trino, dbt, and Gold

Trino 478 uses its Delta Lake connector, native S3 support, and a file metastore stored in MinIO. Register Silver once with `lakehouse.system.register_table`; dbt then builds one staging view and six keyed incremental Delta tables. `MERGE` is required because S3-compatible stores do not support atomic directory rename.

Runtime evidence on 2026-10-24: Trino returned the Spark row (`focus_ratio=0.75`); two consecutive dbt builds each passed 15/15 operations and tests; Gold reconciled to one event and zero stale rows. Local HTTP is intentionally unauthenticated and must not be exposed outside the development host.
