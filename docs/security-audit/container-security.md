# Container security

The main API image runs as UID 10001 and Helm drops all capabilities, forbids privilege escalation, and uses a read-only root filesystem. Spark keeps its upstream user requirements; Airflow root/socket access exists only in the explicitly named development profile. No service is privileged.

Build-context exclusions cover `.git`, local environments, `.env`, datasets, reports, graph outputs and caches. The API Dockerfile no longer accepts MLflow/model URIs as build arguments or downloads artifacts during image construction. CI copies an explicitly selected model and publishes only an immutable commit tag.

Local host ports are loopback-only. Compose credentials are development placeholders and must be overridden outside an isolated workstation. Images are version-tagged but not digest-pinned; add digest update automation and SBOM/signature verification before production.

Trivy 0.76.1 was checksum-verified and executed. Airflow, SeaweedFS, Spark runner, dbt, Flink and the API declare explicit non-root users. The API runtime no longer installs curl and removes unused pip/setuptools after dependency installation; its exact rebuilt image passed production smoke tests as UID 10001 with zero fixable High/Critical findings.

The upgraded Airflow 3.3.2, SeaweedFS 4.50, dbt, Flink and API images have zero fixable High/Critical findings. Spark 3.5.5 reports 126 High/Critical occurrences: 122 with reported fixes, 4 without, 107 distinct IDs and five Critical occurrences. Its non-root, read-only, internal-network, authenticated execution boundary reduces reachability but does not patch the image; SEC-022 is accepted risk for local development only through 2027-01-23.

Candidate scans on 2026-10-25 rejected both official upgrade paths. Spark 3.5.9 (`sha256:af02a4…`) reported 719 High/Critical occurrences (181 with fixes, 538 without), 699 distinct IDs and 29 Critical occurrences. Spark 4.1.3 (`sha256:bf9d03…`) reported 720 (184 with fixes, 536 without), 685 distinct IDs and 27 Critical occurrences. Each contained 641 Ubuntu findings plus 78 or 79 Java findings. Neither image became the approved runtime.
