# Cloud-deferred requirements

No GCP services, Terraform apply, remote Kubernetes deployment, managed Kafka, or paid storage were used. GKE identity, durable production metastore, object-store IAM/KMS, multi-broker Kafka, HA Flink/Airflow, remote secrets, autoscaling, disaster recovery, and an actual 100GB+ benchmark remain deferred to an approved final deployment phase.

Implementing the bounded generator is not evidence that 100GB was processed.

The four cloud points remain individually unverified:

| Criterion | Source status | Runtime status / blocker |
|---|---|---|
| MinIO on GCE/GKE | Blocked | OSS MinIO is unmaintained; AIStor license or instructor equivalence decision required |
| Flink on GCE/GKE/Dataproc | Local manifests/runtime only | Needs an approved cluster, immutable publication, namespace identity and checkpoint recovery proof |
| Spark on GCE/GKE/Dataproc | Blocked by SEC-022 | Existing Spark image is local-development-only; a scanned compatible replacement must pass Delta/S3A/Trino/dbt before cloud use |
| Airflow on GCE/GKE/Composer | Local DAG/runtime only | Needs an approved deployment, secrets/IAM, persistent metadata and execution evidence |

No checked-in configuration is cloud-runtime evidence. Future implementation
must use separate namespaces/service accounts, internal networking, bounded
resources, immutable images, managed secrets, health checks, evidence capture,
cost limits and an independently approved teardown.
