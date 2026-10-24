# Module II resource budget

Baseline on 2026-10-24: 15 GiB RAM total, 3.6 GiB available, 13 GiB swap used; 263 GiB disk free; `/tmp` had 1.3 GiB free. Running everything together is unsafe.

| Profile | Services | Memory limits | Expected active total |
|---|---|---:|---:|
| ingestion | Kafka | 768 MiB | <1 GiB |
| lake | MinIO + initializer | 512 MiB + transient 64 MiB | <0.7 GiB |
| batch | one local Spark driver | 1792 MiB | <1.8 GiB |
| analytics | Trino + dbt runner | 1280 + transient 512 MiB | <1.8 GiB |
| orchestration | Airflow + idle dbt runner | 640 + 384 MiB | <1.1 GiB |
| streaming | Flink JM/TM + Redis | 640 + 768 + 192 MiB | <1.7 GiB |
| observability | existing six-service stack | previously runtime-tested separately | never combined by default |

## Operating rules

- Start only the current checkpoint; stop it before the next heavyweight engine.
- Spark and Flink never run concurrently on this host.
- Use tiny fixtures (tens of events) for integration; medium/large generation requires explicit opt-in.
- Container logs rotate; JVM heaps and task slots are bounded.
- Named volumes are preserved on `down`; deletion requires an explicit cleanup command and user approval.

Safe inspection and shutdown:

```bash
docker compose -f infra/module2/docker-compose.yml ps
docker stats --no-stream
make module2-stop
du -sh data .dvc-storage 2>/dev/null
```

The 100GB+ profile will enforce a configured byte ceiling and free-space reserve. Merely implementing it will not be reported as execution evidence.
