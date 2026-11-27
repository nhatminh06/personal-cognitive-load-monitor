# G1D.1 production outbox source integration — local qualification

Date: 2026-11-27. Local source revision: `a195607d36df61141671345abcc1bf81712bc289` with unpublished worktree changes. Remote `main` could not be refreshed because GitHub DNS resolution failed; the previously observed merged G1B PR #58 remains the baseline. No Git history or retained resource was changed.

## Scope and invariants

Changed only `deploy/cloudflare/src/worker.ts`; added `deploy/cloudflare/migrations/0002_outbox.sql`, `deploy/cloudflare/tests/outbox-integration.mjs`, and this report. The applied `0001_focus.sql` is unchanged. The production Worker and D1 are unchanged.

`OUTBOX_ENABLED` must be exactly `true` to append an outbox insert to the existing D1 `db.batch()` for newly accepted session creation, lifecycle, behavioral-window, and effort events. The outbox insert uses the event's persisted JSON bytes, SHA-256 digest, event ID, owner, session, and sequence. An identical replay returns before the batch and creates no second row. The existing CAS guard, event uniqueness, lifecycle uniqueness, response codes, and failure responses remain in place. A batch failure rolls back both the business mutation and outbox insert. With the flag absent or any other value, no outbox query or write is made, so the existing deployed schema remains sufficient. There is no scheduled dispatch, external fetch, or dispatch route in the production Worker.

The forward-only candidate migration adds the G1B outbox schema and indexes. `delivery_order` orders accepted rows; the unique event ID prevents duplicate delivery records. Its partial unique index applies only to positive lifecycle sequences, while multiple activity and effort rows with sequence zero are valid. The G1B.2 `dispatchBatch`, `inspectDead`, and `reconcile` implementation remains in the isolated prototype and is reused as the future dispatch component; it is not imported into the production entrypoint. It retains bounded batches, HMAC, leases, retry/dead-letter transitions, and per-session order.

## Local evidence

| Check | Result |
|---|---|
| Disposable workerd/D1 migration and Worker mutation test | PASS: pre-existing synthetic row preserved; disabled writes had no outbox; three concurrent identical creates yielded one new and two replays; owner and identity conflicts rejected; lifecycle and two sequence-zero event types persisted; deliberate outbox trigger failure rolled back session and event. |
| Existing D1 atomicity and session-create race tests | PASS: 4 tests total including the new integration test. |
| G1B outbox, gateway, dispatcher, and G1B.3 runtime tests | PASS: 37 tests including the new integration test; lease recovery, retry, dead letter, ordering, reconciliation, and no anonymous dispatch covered. |
| Worker TypeScript typecheck | PASS using installed TypeScript 5.9.3. |
| Wrangler dry-run bundle | PASS; no publication. Wrangler could not write its optional log file under the read-only home configuration, but generated the bundle. |
| Frontend build, typecheck, lint and state test | PASS: one frontend test. |
| Ruff | PASS. |
| `git diff --check` | PASS. |
| `make test` | PASS: 714 passed, 2 skipped, 87% coverage (81% required). The first sandboxed attempt stalled in a tracing test because loopback sockets were blocked; the unrestricted local rerun completed. |
| Existing Worker security/store tests | PASS: 5 tests. |
| Focus-session Python contract/activity tests | PASS: 101 tests. |

The new test verifies event and outbox counts and matching persisted payload identities. Existing G1B tests exercise retries, lease recovery, dead letters, reconciliation, and restart. They use disposable workerd/D1 and a mock gateway. This does not prove external HTTPS, real Kafka, or live Cloudflare CPU behavior. A prior G1B.3 aggregate CPU measurement is historical evidence and cannot qualify this changed Worker.

SHA-256: `worker.ts` `6bdc41911f1c8c072e8a1558f8af9ac9a86ac377e5423c8db14bfb1efc4e2435`; `0002_outbox.sql` `56d6b5be34f30a9e9c121bcc022b2b78744d5396ac1e8ad91e29cc95a573929d`; `outbox-integration.mjs` `e9d7860b11b9ea122f590ece788cdb9b5d38b9879332593ee6ac2bdc5db4cbdd`.

## Review-only production sequence

1. Obtain and independently verify a restorable D1 backup/export and recovery window. Record counts and IDs for sessions, events, estimates, browser sessions, and indexes. Do not treat an application flag as a schema rollback.
2. Review D1 Free row/write limits, database size, migration compatibility, and current Workers Free CPU budget. Apply the forward migration through Wrangler's tracked migration workflow once, with the flag off. A direct second SQL execution fails on existing table/index names; Wrangler migration history is the intended repeat-run guard. On migration failure, leave the flag off, inspect partial state, and restore the verified backup if needed. Do not edit `0001_focus.sql` or drop existing data.
3. Decide separately whether historical events will be backfilled. This source change enqueues only newly accepted events. An old event replay is not a new acceptance and does not create an outbox row. Any backfill needs explicit scope, privacy review, checkpointing, stable IDs, and count reconciliation before external delivery.
4. In a separately authorized release, enable `OUTBOX_ENABLED=true` only after migration verification. Compare new event IDs with outbox event IDs, counts, payload digests, oldest pending age, and failed writes. Measure live Worker CPU per endpoint and daily D1 operations before claiming Free compatibility. If errors occur, disable the flag to restore the old write path while preserving pending rows; restore the prior Worker version if needed. Do not drop the table as routine rollback.
5. External dispatch remains disabled. A future secured HTTPS gateway needs a separately reviewed endpoint, TLS validation, least-privilege synthetic credentials stored as Worker secrets, HMAC replay protection, timeout and rate limits, privacy-minimized payloads, reconciliation, and a bounded scheduler. No secret belongs in static assets or repository configuration. No D1/Kafka exactly-once guarantee is claimed.

`DEFER_SPARK_ENFORCED` and `DEFER_KFP` remain active. The G1C Spark security report is blocked and does not affect this source-only path.
