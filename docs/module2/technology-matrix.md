# Module II technology matrix

Pinned versions favor a known-compatible Spark/Delta generation and maintained container tags over independently choosing latest releases.

| Component | Pin | Runtime | Compatibility decision |
|---|---:|---|---|
| Kafka | 3.9.2 | Java 17 container | Single combined broker/controller is explicitly development-only; KRaft removes ZooKeeper. |
| MinIO | `RELEASE.2025-04-22T22-12-26Z` | image built from official pinned source | Public binary registries rejected anonymous pulls in this environment; the local image compiles the signed upstream tag. Credentials come only from environment. |
| Spark | 3.5.5 | official Python image, Java 11 | Spark 3.5 supports Java 11/17. Local mode only. |
| Delta Lake | 3.3.2 | Spark packages | Delta 3.3.x is the documented line for Spark 3.5.x. Scala artifact `_2.12`. |
| Hadoop AWS | 3.3.4 | Spark package | Matches Spark 3.5.5's Hadoop 3.3.4 distribution for S3A/MinIO access. |
| Trino | 478 | Java container | Selected to match the version explicitly tested by dbt-trino; Delta connector uses native MinIO-tested S3 support. |
| dbt-trino | 1.10.3 | Python 3.11 container | Adapter declares dbt-core `>=1.8,<2.0` and tests against Trino 478. |
| Airflow | 2.10.5 | official Python 3.11 image | Stable pinned image; LocalExecutor/SQLite avoids PostgreSQL/Celery for this constrained demo. |
| Flink | 1.20.5 | Scala 2.12, Java 17 | Maintained 1.20 image; KafkaSource/KafkaSink APIs and checkpointed offsets. |
| Flink Kafka connector | 3.3.0-1.20 | job JAR | Connector release targets Flink 1.20; broker compatibility follows Kafka client protocol. |
| Redis | 7.4.2-alpine | container | Small footprint, persistence enabled, timestamp compare before update. |
| Python clients | `confluent-kafka`, `boto3`, `redis` | API/workers | Mature clients with bounded timeouts; exact Python pins will enter `uv.lock`. |

Primary compatibility references:

- Delta/Spark matrix: https://docs.delta.io/releases/
- Spark 3.5 Python/Java requirements: https://spark.apache.org/docs/3.5.7/api/python/getting_started/install.html
- Kafka KRaft development combined mode: https://kafka.apache.org/39/operations/kraft/
- Flink Java 17 and Kafka connector: https://nightlies.apache.org/flink/flink-docs-release-1.20/docs/deployment/java_compatibility/ and https://nightlies.apache.org/flink/flink-docs-release-1.20/docs/connectors/datastream/kafka/
- Trino Delta and MinIO-tested S3 support: https://trino.io/docs/current/connector/delta-lake.html and https://trino.io/docs/current/object-storage/file-system-s3.html
- dbt-trino compatibility: https://github.com/starburstdata/dbt-trino
- Airflow pinned image: https://hub.docker.com/r/apache/airflow/tags?name=2.10.5

These are intended pins, not runtime proof. Each image/connector must pass its checkpoint before it is marked verified.
