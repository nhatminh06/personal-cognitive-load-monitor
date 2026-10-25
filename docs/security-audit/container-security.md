# Container security

The main API image runs as UID 10001 and Helm drops all capabilities, forbids privilege escalation, and uses a read-only root filesystem. Spark keeps its upstream user requirements; Airflow root/socket access exists only in the explicitly named development profile. No service is privileged.

Build-context exclusions cover `.git`, local environments, `.env`, datasets, reports, graph outputs and caches. The API Dockerfile no longer accepts MLflow/model URIs as build arguments or downloads artifacts during image construction. CI copies an explicitly selected model and publishes only an immutable commit tag.

Local host ports are loopback-only. Compose credentials are development placeholders and must be overridden outside an isolated workstation. Images are version-tagged but not digest-pinned; add digest update automation and SBOM/signature verification before production.

Trivy 0.76.1 was checksum-verified and executed. Airflow, SeaweedFS, Spark runner, dbt, Flink and the API declare explicit non-root users. The API runtime no longer installs curl and removes unused pip/setuptools after dependency installation; its exact rebuilt image passed production smoke tests as UID 10001 with zero fixable High/Critical findings.

The upgraded Airflow 3.3.2, SeaweedFS 4.50, dbt, Flink and API images have zero fixable High/Critical findings. The expanded scan is still not accepted for merge because Spark 3.5.5 reports 122 fixable High/Critical occurrences (103 distinct IDs), including five Critical occurrences. Its non-root, internal, authenticated execution boundary reduces reachability but does not patch the image; SEC-022 requires a maintained Spark/Delta/base-image upgrade and complete regression.
