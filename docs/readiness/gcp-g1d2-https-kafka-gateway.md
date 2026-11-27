# G1D.2 secure HTTPS → Kafka boundary — local qualification

**Decision: `GCP_G1D2_LOCAL_HTTPS_KAFKA_PASS` for the bounded local synthetic path.** Date: 2026-11-27. Source HEAD `a195607d36df61141671345abcc1bf81712bc289`; existing unpublished worktree changes were preserved. No production Worker, D1, DNS, GCP, Spark, KFP or Git publication changed. This result does not qualify public ingress, a distributed production gateway, or Cloudflare Free CPU.

## Source and trust boundaries

The existing G1B.4 Kafka gateway moved into `deploy/cloudflare/gateway/kafka_gateway.py`; its old path is a compatibility import for existing tests. New `server.py` and `README.md` define a TLS-only, loopback, single-host deployment source candidate with privately mounted certificate, key and versioned HMAC key map. The G1B.2 dispatcher is reused and now accepts a bounded key ID and an explicit `GATEWAY_REQUIRE_HTTPS=true` guard. The local driver sets that guard. No production dispatcher route, schedule, flag or outbound destination was enabled.

The dispatcher signs exact envelope bytes using HMAC-SHA256 and a timestamp/UUID nonce. The TLS client trusts only the disposable test CA and checks `localhost` against the certificate SAN; no verification bypass is used. The gateway checks key ID, constant-time signature equality, a 30-second timestamp window, unique nonce, 8 KiB request cap, 4 KiB payload cap, SHA-256 payload digest, stable event/session/sequence identities, supported event type and full canonical Pydantic schema. It rejects non-synthetic source/subject values for this qualification. A shared SQLite file durably stores nonces, broker receipts and attempts across local gateway restarts and two local instances. Admission is limited to eight concurrent handlers, a 60-second request window, a five-second client read timeout and a bounded Kafka producer queue. Application request bodies, secrets and authorization headers are not logged.

The gateway publishes with the session ID as Kafka partition key, `acks=all`, producer idempotence, a bounded retry/timeout, then commits its receipt before HTTP 200. The durable consumer stores an event ID/digest before committing Kafka offset. A Kafka ack followed by a failed receipt commit can yield another Kafka record on retry. Therefore this is **at-least-once delivery with downstream idempotent materialization**, never an end-to-end exactly-once claim. HTTP 504 after a successful receipt was injected and recovered by same-ID retry.

The broker was an exact cached `cogniflow-kafka:c43-patched` image, ID `158594103c0e`, in task-owned container `cogniflow-g1d2-kafka-20261127` (`3bd363962f5d30f1b7e920c4d9ee77c69e11787a6356adb7ffac0b5b57bd7acc`), with its own volume, 1 CPU, 768 MiB memory and loopback-only port `127.0.0.1:39095`. The image provenance/security result is retained historical G1B.4 evidence, not a fresh image scan. Local Kafka used one plaintext loopback broker and one replica. HMAC authentication was required **before gateway Kafka publication**; production broker transport/ACLs remain a separate security gate.

## Executed integration and failure matrix

The final script used a temporary CA and hostname-bound server certificate, generated synthetic HMAC keys, disposable Miniflare D1 and SQLite ledgers, the actual TLS client, and real Kafka publication and consumption. Temporary certificate/key/database directories were removed by the test harness. The final non-secret JSON is `/tmp/cogniflow-g1d2-final.json`, SHA-256 `bc6afef5b73d2431057156c51201ce29b7ab68e815be2ee7e48c72bd366949b0`.

| Case | Local observation |
|---|---|
| Valid D1 outbox → dispatcher → verified HTTPS → Kafka → consumer | One accepted event was acknowledged in D1 and durably consumed. |
| Bad signature, expired timestamp, nonce replay, wrong key after rotation | Rejected with 401 or 409 before publication. Same nonce was rejected after restart and by a second local gateway instance sharing the durable store. |
| Wrong hostname or untrusted CA | TLS connection rejected by the client. |
| Malformed sequence, oversized body, unsupported event type/schema | Rejected with 422 or 413. A separate security test verified a request cap returns 429. |
| Lost HTTP acknowledgment after broker success | Gateway returned 504; dispatcher retried the same event ID and reached acknowledged through the durable receipt, without another logical gateway publication. |
| Gateway unavailable and broker stopped | Outbox stayed retryable. The exact task-owned broker was restarted; the pending event then published and acknowledged. |
| Concurrent dispatchers | Two local dispatcher calls claimed one D1 lease; one delivered the event. Existing G1B tests cover stale-holder fencing, lease expiry and ordering. |
| Terminal gateway rejection | D1 row remained inspectable in `dead` state. |
| Secret rotation | Old and new key IDs both worked during overlap; the old ID failed after restart with only the new key mounted. |
| Gateway and consumer restart, duplicate Kafka record | Receipts and nonce claims survived gateway restart. A separately published duplicate Kafka record was consumed after consumer restart: 6 records, 5 logical IDs, 1 duplicate. |

Final gateway ledger: 5 broker-acknowledged publications, 5 duplicate HTTP attempts handled from receipts, 5 distinct consumer IDs, one deliberate dead letter, 21 measured gateway requests. Reconciliation of acknowledged outbox IDs, gateway receipts and durable consumer IDs was checked by the existing G1B suites; the new TLS test compared receipt and logical consumer counts. No unexpected resource-limit or OOM failure occurred. The deliberate 429 test is an admission-control result, not a resource-limit error.

## Resource measurements and regression

Final bounded run: gateway handler wall-time maximum **3,001.046 ms** during the deliberate broker outage; handler-thread CPU maximum **65.298 ms**; combined Python test/gateway process peak RSS **65,880 KiB**; Kafka producer acknowledgment maximum **332.263 ms**. The first local dispatcher delivery took **108.015 ms wall time**, used 2 D1 operations and one HTTPS request for a 376-byte payload. These are local process/thread and wall measurements, **not Cloudflare Worker CPU**. One broker `docker stats` sample was 3.76% CPU and 399.7 MiB memory; cgroup peak was 425,652,224 bytes, OOM false, container restart count zero before scoped removal. Manual broker stop/start was intentional. Cloudflare Free CPU remains **UNVERIFIED**.

- Local real TLS/Kafka test including broker outage/restart and duplicate consumption: PASS.
- G1B outbox/dispatcher plus G1D.1 workerd/D1 tests: **38 passed**.
- Existing G1B.4 security tests plus new 429 test: **3 passed**.
- `make test`: **714 passed, 2 skipped**, 87% coverage (81% required).
- Ruff, Python compile, Node syntax and `git diff --check`: PASS.
- Broker stderr marker scan found no secret, credential, payload or private-key text. Generated CA, server key, secret values, D1 and receipt databases were confined to temporary paths and removed; only non-secret JSON/connection diagnostics remain under `/tmp`.

## Source hashes and cleanup

SHA-256: `gateway/kafka_gateway.py` `911ba14d0c95032e444c8c1ab59ffa51d5722a7b89bc3b16e3e007b986647cb6`; `gateway/server.py` `935289ba52230c9e3a01979059bd807f7ee4566f86d7d07aae5316201324f434`; `gateway/tls_dispatch.mjs` `4dc0d0aa24efaa5414ebc8835ed105659e243cd84465adf9ee41ed0b3fd9f8c6`; `gateway/local_tls_test.py` `e3bc0e05d6e0b1fa94d21f1ba01b17a3add874e612eb1f16948ea965bfb0ecbe`; `gateway/README.md` `e0906c9c311571435a4cd2b2a2175798664d685d0a2af83190d8d4859b76e44e`; `g1b2-gateway/dispatcher.mjs` `c06a56f379ebc606fabfc6af73944a6dc93037eecb6a808c5d6a77d76c9f50c4`; compatibility `g1b4-kafka/gateway.py` `3411ab0d395cdded39cc7baf5646717b8d7278d212a0260b60df85a206568de3`; `g1b4-kafka/security_test.py` `64686d74f0d0cc57652126b467dd4816bdd07e35fc2204aa683ede0bd9321081`.

The exact task-owned Kafka container and volume `cogniflow-g1d2-kafka-data-20261127` were removed and absence verified. No G1D.2 container or volume remained. The retained `cogniflow-module1-qualification-control-plane` container (`b5139d30ad2d`) remained running; it was never mutated. Temporary TLS files, SQLite files and synthetic keys were removed by `TemporaryDirectory`. No public port, cloud resource, production credential or production migration was created or changed.

## Remaining production gates

The current gateway package is a **single-host source candidate**, bound to loopback and a test-topic prefix. A production multi-host ingress requires a shared transactional nonce/receipt store with retention and recovery, Kafka authentication/ACLs and encrypted broker transport or a reviewed private sidecar, ingress network policy, certificate management, operational rate limits, and public TLS/security testing. The local two-instance shared-file test does not establish cross-host replay safety. Production dispatch scheduling, secret distribution, privacy review, backfill, live D1 migration, Cloudflare CPU profiling and Free-plan quota review remain separately authorized work. `DEFER_SPARK_ENFORCED` and `DEFER_KFP` remain active.
