# Module I — disposable MLMD crash diagnostic (2026-11-21)

**Status: BLOCKED_PRECHECK.** No diagnostic workload was run. The owner authorized a Docker-only test conditional on proving that daemon startup would preserve existing resources. Docker service and socket were both inactive, and existing container restart policies could not be inspected without starting Docker. Starting the daemon could restart unrelated containers. The explicit fail-closed preflight therefore stopped the task before any Docker API call, image execution, or cluster access. `DEFER_KFP` remains in force.

## Preflight evidence

| Check | Result |
|---|---|
| Git | Branch `main`, HEAD `e9cefee6a99e25cad1bce73b78948398ad5b23b8`; pre-existing modified/untracked files preserved. |
| Docker | Read-only `systemctl show` reported `docker.service` **inactive/dead** and `docker.socket` **inactive/dead** before and after preflight; `containerd.service` inactive/dead. No daemon start was attempted. |
| Existing resources | `/var/lib/docker/containers` was inaccessible to the diagnostic user. Existing container restart policies and auto-start behavior are **UNVERIFIED**. No resource was intentionally modified. |
| Exact image | Intended local image: `cogniflow-mlmd@sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876`. Local presence **UNVERIFIED** because an image-inspect API call could activate Docker. No pull or substitution occurred. |
| Host | About 10 GiB available RAM and 142 GiB free disk at preflight. `docker`, `gdb`, `eu-stack`, and `coredumpctl` executables exist; debugger and symbol usability for the image were **not tested**. |
| Isolation design | A `--network none` reproduction might exercise an unavailable-database error, but it would not reproduce C22's live MySQL invalid-password path. A faithful test would need only a task-owned network and database. Neither design was executed because preflight failed. No kernel, ptrace, privilege, host PID/network or host-wide core setting was changed. |

The required [crash investigation](module1-mlmd-startup-crash-investigation-2026-11-21.md), [evidence-recovery addendum](module1-mlmd-crash-evidence-recovery-addendum-2026-11-21.md), and [KFP2 reconciliation](module1-m1-kfp2-evidence-capacity-reconciliation-2026-11-21.md) were reviewed. The retained C22 tool call and output are at `/home/pnmynh/.codex/sessions/2026/11/19/rollout-2026-11-19T21-52-48-01a1f715-e014-76f3-93f2-4fd5cfcfcce1.jsonl`, lines 2440 and 2442. They record an invalid test password, failed `mysql_real_connect`, fatal startup check at `metadata_store_server_main.cc:555`, exit 139 and `OOMKilled=false`. That is **historical evidence**, not a fresh result. The source session was not copied because it may contain private data.

## Diagnostic result and limits

- **Reproduction:** BLOCKED_PRECHECK; no fresh process exit, signal or OOM observation.
- **Native backtrace:** UNVERIFIED; no core or debugger output was produced. The historical log has a stack-trace header without frames.
- **Root cause:** The retained evidence supports failed database initialization reaching MLMD's fatal startup check. The instruction or linked function producing SIGSEGV remains UNVERIFIED. No entrypoint, manifest, credential, source or image change was made.
- **Configuration-only correction:** Not established. Credential readiness or probes could address startup timing, but cannot be claimed to fix the recorded invalid-credential failure or its exit behavior.
- **Security/runtime boundary:** The active MySQL image still lacks exact matching security evidence; S3 MLflow and GCS ledger identities differ; published signed KFP artifacts and real runtime qualification remain pending. `DEFER_KFP` stays active.

## Evidence, cleanup, and next action

Task-owned ignored evidence is `build/mlmd-disposable-crash-diagnostic-2026-11-21/preflight.json` with `SHA256SUMS`. This report is the only new tracked-path file. No container, network, volume, image, daemon or Kubernetes resource was created or changed, so no infrastructure cleanup was needed. Docker service and socket remained inactive/dead at the final read-only check. No commit or push occurred.

**Smallest next action:** obtain a read-only, authoritative inventory of every existing Docker container's restart policy and daemon startup behavior, plus read-only confirmation that the exact MLMD image is locally present, without activating Docker. Only once startup safety is demonstrated should the already-authorized bounded diagnostic proceed in a separate task. Do not use retained kind clusters or production credentials.
