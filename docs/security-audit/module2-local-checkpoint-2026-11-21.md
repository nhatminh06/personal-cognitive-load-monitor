# Module II local streaming checkpoint — 2026-11-21

## Kafka remediation

- CVE-2026-109908 (HIGH).
- libfontenc upgraded from 1.1.9-r0 to 1.1.10-r0.
- Patched Kafka scan: 0 HIGH, 0 CRITICAL.
- Broker restarted with persistent volume retained.
- All seven topics remained available.

## Image identities

- Kafka: sha256:158594103c0e9a9986fd599043af25ed2a4a9a50f5925d4234a5b8dba6eb06a0
- Flink: sha256:3147c3a836514a84acd7eb41568e33e408f0d49866c36d17f690926334b15ecb
- Redis: sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe

## Security evidence

All three images reported zero HIGH and CRITICAL findings.

Scan report SHA-256 checksums:

- Kafka: 3044c5add00bf027baa0150b43da49657d7456598c8167b1ae9492431d64fd78
- Flink: ac6a391e2173c2dd0355b33d78166401b7059b5ae03f80944b5b5057f934ed04
- Redis: 5804fa07e41ccc911057a1c036c61dfa170135d8341d84e90614ece3201c493b

Raw reports retained locally under build/security-scans/.

## Streaming runtime evidence

- Timestamp: 2026-11-21T08:46:25Z
- Session: flink-smoke-4982cf61-78c7-4111-a5d7-7c5fe19fc953
- Status: PASS
- Initial events published: 3
- Duplicate Redis unchanged: true
- Older Redis rejected: true
- Optional counts null: true
- Feature partition/offset: 0/0
- DLQ partition/offset: 0/0

## Qualification boundary

Bounded local behavioral streaming smoke test passed.
Full Module II rehearsal remains unqualified.
Checkpoint recovery was not retested.
Existing image identity gates remain unchanged.
Spark remains security blocked.
No cloud or production deployment authorized.

