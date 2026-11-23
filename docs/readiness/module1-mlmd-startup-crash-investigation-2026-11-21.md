# Module I — MLMD startup crash investigation (2026-11-21)

## 1. Executive summary

**Final MLMD decision: BLOCKED.** The retained C21/C22 evidence establishes a reproducible invalid-credential failure of the selected MLMD 1.14 image: MySQL authentication fails, then the MLMD process exits 139 (SIGSEGV). The native faulting instruction and call stack are not retained, so the precise binary root cause is **UNVERIFIED**. No fix was implemented. `DEFER_KFP` remains in force; this assessment neither clears the active MySQL image nor resolves the separate MLflow ledger mismatch.

## 2. Exact failure and deployment evidence

| Item | Verified evidence | Scope |
|---|---|---|
| Selected MLMD local image | `sha256:d17f04d9138660061f3bca87d3cfae06a812781e3fae0aa03330443f08544876` in the [current render](../../build/kfp-source-check.15ctzKrx/kfp-headless-render.yaml) and [C21 assessment](../course-completion/c21-evidence/assessment.json) | Local image ID, not a published OCI manifest digest |
| Server binary | `/bin/metadata_store_server`, SHA-256 `d170da72e14dfc4726f7f9cfbe48d57cfa4c0dedbe42a8224880be5d879aa584` per [C21 report](../course-completion/c21-kfp-metadata-integration.md); [Dockerfile](../../deploy/c21/mlmd/Dockerfile) copies it unchanged from pinned upstream image `sha256:51404ef4419c1426da80f3e14a83dcb55f65bb5a971371d36d14cec1e50af830` | MLMD 1.14 server, not CogniFlow application code |
| Actual rendered startup path | `/bin/metadata_store_server --grpc_port=8080 --metadata_source_config_type=mysql --mysql_config_database=$(MYSQL_DATABASE) --mysql_config_host=$(MYSQL_HOST) --mysql_config_port=$(MYSQL_PORT) --mysql_config_user=$(DBCONFIG_USER) --mysql_config_password=$(DBCONFIG_PASSWORD) --enable_database_upgrade=true --grpc_channel_arguments=grpc.max_metadata_size=16384,grpc.max_receive_message_length=104857600,grpc.max_send_message_length=104857600` | Kubernetes substitutes Secret and ConfigMap environment variables at process launch; the command is reconstructed from the current render, not the retained C21 Docker invocation |
| Negative test | C21 reports wrong database password, `mysql_real_connect failed`, exit 139. C22 records signal 11, OOM false, zero database tables before/after, no authenticated access, no unauthorized writes and no test password in logs. | Historical local container evidence; no container was run here |
| Positive test | C21 used the then-qualified C18 MySQL image and a dedicated `metadb` account with `mysql_native_password`; schema 10, metadata reads/writes and restart readback passed. | Does not clear the newer active MySQL image or the negative-auth failure |

The exact historical `docker run` command, raw stderr/stdout, core dump and symbolic backtrace were not found in the retained files inspected for this task. Therefore the **exact C21 invocation is UNVERIFIED**; the table gives the **current rendered startup command**, which is a distinct fact. C21/C22 establish that the connection failed before the abnormal exit. Database initialization did not complete in the negative case: C22 observed zero tables before and after. The evidence does not localize the SIGSEGV to a particular MLMD function or prove whether it happened during error handling, teardown or another native path after the failed connection.

The current offline render is SHA-256 `5a7a1e3834503c67f253bb55c897fcf5d53c367359ce2dc75ccf5365985560d1`: 73 resources, 10 Deployments, 16 container image uses, 11 unique images, and two 20 GiB PVCs. The source archive SHA-256 is `4b50a172728854115776532673e0df6d98679fb8303a806d901bb7825e359e55` for KFP commit `7dd28116ad652bfb7b6c282e7920be84e6a7634a`. The older C22 render SHA-256 `6dc13b9fedfb4f8b528f87a5f6be33175bf1a9f29c11c1bf95d279b100f13322` is **different**; no byte equivalence is claimed.

## 3. Root-cause assessment and confidence

- **High confidence — trigger:** The negative test supplied an invalid MySQL password; `mysql_real_connect` failed and MLMD subsequently exited with SIGSEGV. Credential rejection worked; the server did not make unauthorized writes. The absence of an OOM kill excludes memory eviction as the recorded exit mechanism.
- **Moderate confidence — fault domain:** The selected image runs an unchanged upstream native MLMD 1.14 server binary. CogniFlow's patch supplies image, arguments, credentials and security context; it contains no server code. The crash is in the native server process or its linked runtime after connection failure. The exact faulting library/function is **UNVERIFIED** without a backtrace.
- **High confidence — startup ordering limit:** The rendered `wait-for-database` init container uses `nc -z` on MySQL host/port, up to 60 attempts with five-second sleeps. It proves a TCP listener only. It cannot verify that the intended account/password works, that `metadb` exists, or that MLMD schema initialization will succeed. The deliberately wrong-password test would fail even if MySQL had been fully ready.
- **Moderate confidence — configuration contribution:** A wrong password is expected to make MySQL reject the connection; it is not an acceptable reason for a server SIGSEGV. MySQL 8.4's `mysql_native_password` setting is deliberate in the selected KFP 2.18.1 upstream manifest and current patch. The [upstream MLMD issue on MySQL 8 authentication](https://github.com/google/ml-metadata/issues/178) describes this plugin compatibility constraint; it does **not** identify a fix for the observed SIGSEGV.
- **Unverified — exact native root cause:** There is no retained stack trace, core file, source-level fault location, or verified upstream fix commit. The C22 classification of an upstream correctness defect is consistent with the evidence but should not be read as proof of a specific MLMD code defect line.

The current MLMD pod has TCP liveness/readiness probes on port 8080, each starting after three seconds, and no startup probe. TCP success does not verify MySQL authentication or MLMD metadata operations. Liveness restarts could amplify an unavailable-database incident, and a startup probe could avoid premature liveness restarts during slow valid initialization. Neither probe change can prevent the demonstrated wrong-password SIGSEGV or make bad credentials valid. No Kubernetes probe was exercised in C21/C22's local test.

## 4. Remediation options and tradeoffs

| Option | Benefit | Why it is not an established fix now |
|---|---|---|
| Correct credential/Secret handling | Prevents accidental authentication failures; keep credentials in Secret references and validate account scope without printing values. | Does not make MLMD handle bad credentials safely. The current upstream command expands the password into MLMD's process arguments, a separate exposure risk requiring review. Current active MySQL image still lacks exact-image security evidence. |
| Strengthen startup ordering or probes | A database-auth-aware gate could defer MLMD startup until the intended account works; a startup probe could protect slow valid initialization. | The existing TCP gate cannot check authentication. A new helper image/client would require its own provenance, scan and permissions review. Probes cannot fix the native error path, and no supported gRPC health endpoint was verified for this exact binary. |
| Supported upstream MLMD fix/build | Could make connection errors fail cleanly while preserving the MySQL/MLMD contract. | No specific upstream release or patch has been verified to fix this SIGSEGV. Any changed binary requires KFP 2.18.1/schema compatibility review, exact-image 0 HIGH/0 CRITICAL scan, provenance and separate isolated negative/positive tests. No image substitution is authorized here. |
| Restart policy only | May restore availability after transient failures. | Persistent invalid credentials would keep crashing and restarting; this is containment, not correctness. |

**Smallest defensible remediation now:** none to the runtime manifest or image. Obtain the original negative-test command and raw logs if retained, plus a symbolic backtrace for this exact binary in a separately authorized, disposable diagnostic environment. Use that evidence to identify an upstream-supported correction before changing image or probes. A configuration-only change could reduce startup races but cannot be claimed to repair the observed SIGSEGV.

## 5. Offline checks actually executed

- `sha256sum` confirmed current render `5a7a1e3834503c67f253bb55c897fcf5d53c367359ce2dc75ccf5365985560d1` and KFP source archive `4b50a172728854115776532673e0df6d98679fb8303a806d901bb7825e359e55`.
- Parsed the retained render offline: **73 documents, 10 Deployments, 16 image uses, 11 unique images, two PVCs of 20 GiB each**. Inspected the exact MLMD command, init-container TCP wait, Secret references, probes and selected image without contacting a cluster.
- `sha256sum -c build/m1-kfp2-2026-11-21/source-checksums.sha256`: **PASS** for listed local source and assessment files. This does not validate absent raw C21/C22 logs or scan JSON.
- `.venv/bin/pytest -q src/tests/test_c21_metadata_runtime.py src/tests/test_kfp_release_inventory.py src/tests/test_kfp_pipeline.py`: **14 passed**. These are offline contract tests, not a new MLMD container reproduction.
- Ruff and `git diff --check`: **PASS**. No application, Dockerfile, image ledger or deployment configuration changed.

## 6. Tests blocked by this task's environment

No Docker or Kubernetes operation was permitted, so the invalid-password crash was **not rerun**; no current MySQL startup, MLMD readiness/liveness behavior, credential rotation, binary backtrace, alternative MLMD version or real KFP pipeline was tested. Any claim that a probe or wrapper fixes the crash would be **UNVERIFIED**. Historical local negative-auth result remains **FAIL** for graceful credential handling; combined KFP runtime remains **BLOCKED**.

## 7. Files changed

Only this new report under `docs/readiness/`. Existing source, images, containers, databases, clusters, Git history and unrelated working-tree changes were preserved.

## 8. Remaining risks and blockers

The active MySQL image `sha256:febda51c2aa5e451cb2d4161f1c82f731dc5e36cbf06be80eea4ed17e9dcb5e6` still lacks attributable exact-image scan/SBOM evidence. The active S3-oriented MLflow image differs from the GCS release ledger entry. Published/signed runtime image identities and a true KFP run remain unqualified. A bad credential would plausibly cause repeated MLMD restarts in Kubernetes; the rendered TCP probes do not validate metadata service correctness. The exact native crash cause and supported fix remain unknown. `DEFER_KFP`, KServe BLOCKED, Spark BLOCKED, cloud NOT QUALIFIED and production NOT READY remain unchanged.

## 9. Final MLMD qualification decision

| Question | Decision |
|---|---|
| Is the invalid-credential crash real in retained local evidence? | **FAIL** — C21/C22 recorded exit 139/SIGSEGV after failed MySQL authentication. |
| Is the precise root cause established? | **UNVERIFIED** — no backtrace or faulting source location. |
| Was a fix implemented or validated? | **BLOCKED** — no supported correction demonstrated; no runtime change made. |
| Is isolated runtime testing still required? | **YES** — in a separately authorized diagnostic and later security-qualified acceptance path. |
| May KFP deferral be lifted? | **NO** — `DEFER_KFP` remains necessary. |

## 10. Exact next owner action

Provide the retained C21 negative-test invocation, raw stderr/stdout and any core/backtrace if available. If they do not exist, authorize a **separate**, disposable MLMD-only diagnostic using the exact image and a test-owned database after its image-security prerequisites are satisfied. Use disposable credentials, restrict process inspection, redact logs, and explicitly account for the upstream command's password argument. Capture a symbolic stack trace and compare the error path with a specific upstream-supported candidate. This report does not begin that diagnostic or authorize KFP deployment.
