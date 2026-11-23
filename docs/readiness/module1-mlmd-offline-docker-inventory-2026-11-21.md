# Module I — offline Docker safety and image inventory (2026-11-21)

**Final preflight decision: `BLOCKED_PERMISSIONS`.** The offline gate does not authorize starting Docker. No Docker CLI command was run; Docker, `docker.socket`, and containerd remained inactive/dead at the final host check. Container restart policies and the exact target image content could not be read because `/var/lib/docker` requires elevated filesystem access and passwordless sudo is unavailable. `DEFER_KFP` remains in force.

## 1. Docker storage configuration

Read-only host `systemctl show` and unit inspection found:

| Item | Result |
|---|---|
| Docker unit | `/usr/lib/systemd/system/docker.service`; enabled but inactive/dead |
| Docker socket | `/usr/lib/systemd/system/docker.socket`; disabled and inactive/dead; it would trigger `docker.service` if activated |
| containerd | disabled and inactive/dead |
| Docker command | `/usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock` |
| Overrides/environment | No systemd drop-ins, service environment, `RootDirectory`, `RootImage`, `/etc/default/docker`, or `/etc/sysconfig/docker` |
| Daemon configuration | `/etc/docker/daemon.json` absent; no files found under `/etc/docker` |
| Effective data root | `/var/lib/docker`, by Docker's default after excluding daemon JSON, command-line `--data-root`, service overrides, and environment-file configuration; it is a real directory on the root Btrfs filesystem, not a symlink |
| Image-storage backend | `UNVERIFIED`; no `--storage-driver` or daemon setting exists, the accessible journal contained no matching driver entry, and the root-owned image metadata cannot be inspected |
| Access | `/var/lib/docker` is `root:root` mode `0710`; this user cannot traverse its `containers`, `image`, or `overlay2` children; `sudo -n` requires a password |

The filesystem-access limitation is host permission evidence, not evidence that any particular Docker metadata child or storage backend exists. The sandbox initially rendered host ownership as `nobody`; all ownership and service-state statements above come from the approved read-only host inspection.

## 2. Offline container restart-policy inventory

**Inventory status: `UNVERIFIED`.** No `hostconfig.json` or `config.v2.json` could be read. Therefore no container name, ID, restart policy, maximum retry count, last recorded state, manual-stop evidence, or daemon-activation restart classification can be reported defensibly. No complete container configuration was printed or retained.

On-disk state would in any case be a last-recorded snapshot rather than authoritative proof of current runtime behavior. Docker's daemon-level systemd `Restart=always` applies to the daemon process and does not establish any container's restart policy.

## 3. Retained cluster-container restart risks

The containers belonging to `cogniflow-local` and `cogniflow-module1-qualification` could not be identified offline without access to the container metadata. Their restart risk is **`UNVERIFIED`**. Neither retained kind cluster was accessed or mutated. Because an existing container could have `always` or an applicable `unless-stopped` policy, Docker activation is not safe to authorize from the available evidence.

## 4. Exact MLMD image availability

Target: `cogniflow-mlmd@sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876`

**Image result: `UNVERIFIED`.** Root-only Docker image metadata and content were not read. Historical repository evidence identifies the same hex value as a **local image configuration ID**, not a proven OCI manifest digest. A digest string in a render, assessment, repository metadata, or a configuration blob alone would not prove the requested repository-digest association or that every image layer is retained and readable.

The following remain separately unverified:

- configuration blob `sha256:d17f04...44876`;
- an OCI/Docker manifest whose digest is `sha256:d17f04...44876`;
- the `cogniflow-mlmd` repository association for that manifest digest;
- all referenced layer blobs/diff IDs and their applicable content/snapshot data;
- current runnability of the locally retained content.

Accordingly this report does not promote the historical C21/C22 identity evidence to a fresh local-content pass and does not return `PARTIAL_LOCAL_EVIDENCE` merely because the digest appears in tracked files.

## 5. Decision

`BLOCKED_PERMISSIONS`

The required metadata cannot be inspected by the current user. This decision precedes and is narrower than `BLOCKED_RESTART_RISK` or `BLOCKED_IMAGE_IDENTITY`: neither prerequisite can yet be evaluated. Do not activate Docker, its socket, or containerd, and do not resume the disposable MLMD diagnostic automatically.

## 6. Owner action required

An owner with root read access should run a narrowly scoped offline collector while all three units remain inactive. It should:

1. fail closed unless `docker.service`, `docker.socket`, and `containerd.service` are all inactive;
2. read only `/var/lib/docker/containers/*/{hostconfig.json,config.v2.json}` and emit only ID, name, restart-policy name, maximum retry count, last-recorded running/status fields, and any explicitly present manual-stop field;
3. read only the applicable `/var/lib/docker/image/<driver>/repositories.json`, `imagedb/content/sha256`, layer metadata, and—if this installation uses containerd image storage—the relevant content metadata/blobs;
4. prove separately the configuration ID, manifest digest, `cogniflow-mlmd` repository-digest association, and presence of every referenced layer;
5. recheck unit inactivity after collection and provide the sanitized output for review.

Suggested discovery commands (read-only and intentionally not executed here) are:

```bash
sudo find /var/lib/docker/containers -mindepth 2 -maxdepth 2 \
  -type f \( -name hostconfig.json -o -name config.v2.json \) -print
sudo find /var/lib/docker/image -maxdepth 5 -type f \
  \( -name repositories.json -o -path '*/imagedb/content/sha256/*' \
     -o -path '*/layerdb/sha256/*/*' \) -print
sudo find /var/lib/docker -maxdepth 4 -type d \
  \( -name content -o -name overlay2 -o -name containerd \) -print
```

These discovery commands should be followed by a purpose-built sanitizer; do not copy or print complete container configs because they may contain environment values, mounts, labels, or secrets. If temporary root-owned output is needed, place it in an owner-controlled directory, restrict it to mode `0700`, and retain only the sanitized projection.

## Evidence retention and scope

Sanitized evidence is retained under ignored `build/module1-mlmd-offline-docker-inventory-2026-11-21/` with `SHA256SUMS`. It records unit/configuration/storage-access facts and explicit unavailable classifications; it contains no container configuration, environment variables, credentials, image blobs, or Kubernetes data. No service, socket, container, image, Docker storage, Kubernetes resource, tracked unrelated file, commit, or remote was modified.
