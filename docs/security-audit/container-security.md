# Container security

The main API image runs as UID 10001 and Helm drops all capabilities, forbids privilege escalation, and uses a read-only root filesystem. Spark keeps its upstream user requirements; Airflow root/socket access exists only in the explicitly named development profile. No service is privileged.

Build-context exclusions cover `.git`, local environments, `.env`, datasets, reports, graph outputs and caches. The API Dockerfile no longer accepts MLflow/model URIs as build arguments or downloads artifacts during image construction. CI copies an explicitly selected model and publishes only an immutable commit tag.

Local host ports are loopback-only. Compose credentials are development placeholders and must be overridden outside an isolated workstation. Images are version-tagged but not digest-pinned; add digest update automation and SBOM/signature verification before production.
