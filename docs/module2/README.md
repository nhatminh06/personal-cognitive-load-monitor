# Module II local data platform

Module II adds a local-first, profile-isolated Kafka → MinIO → Spark/Delta → Trino/dbt batch path and Kafka → Flink → Redis streaming path. Module I `/predict` remains independent. See [architecture](architecture.md), [demo script](demo-script.md), and [testing evidence](testing.md).

No cloud resources are provisioned. Keep only one heavyweight profile active and finish with `make module2-stop`.
