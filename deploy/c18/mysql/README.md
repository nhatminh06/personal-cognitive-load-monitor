# C18 KFP MySQL runtime

This image packages only the official MySQL 8.4 server-minimal RPM on a
digest-pinned Oracle Linux base. It retains the entrypoint from the exact
upstream KFP MySQL image but does not copy MySQL Shell or its Python/OCI tree.

Build with bounded resources:

```bash
docker build --memory 4g --cpu-quota 200000 \
  --tag cogniflow/mysql:8.4.13-c18-minimal deploy/c18/mysql
```

The KFP manifest must change its MySQL pod and filesystem group from upstream
UID/GID `999` to the RPM-created UID/GID `27`. Do not deploy this local image
ID directly. Publish the qualified bytes, resolve the remote OCI digest, sign
and attest that digest, and then supply it through the C11 image ledger.

The image initializes `mlpipeline`, `cachedb`, and `metadb`. Credentials remain
runtime inputs; no credential is embedded in the image.
