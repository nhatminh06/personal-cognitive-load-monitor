# C7 Knative Eventing and anomaly qualification

**Date:** 2026-11-18. **Decision:** `PASS_LOCAL` for the isolated application
pipeline. This is not a fresh Knative Broker/Trigger acceptance and does not
complete Module III.

## Exact images and security result

Both images were built from committed revision
`1eb7ff174ae3873f8bb2a87f3b96331d07b29e4c` with hash-locked Python
dependencies, pinned Wolfi and uv inputs, BuildKit `mode=max` provenance and
SBOM attestations, and UID 65532. The alert sink uses the anomaly image with its
sink command.

| Component | Local OCI index ID | Runtime manifest | Trivy HIGH / CRITICAL |
|---|---|---|---:|
| Event consumer | `sha256:05291fa37377d764d62892685a7814ab208ce7f740e1bbf5ec200b16784cbdb0` | `sha256:3723e3346136395f20fcd20b7050e368a1d48534348a16e6cc049200d8c69277` | 0 / 0 |
| Anomaly detector and alert sink | `sha256:debca2c101ae18c2f32626cfa558573c44965ebc83a4b23a0fba90aace900f32` | `sha256:a404935e24a967bc910966cbeb1f72fb2b8b44259c8637dbf0271558fbb06d11` | 0 / 0 |

Trivy 0.76.2 used vulnerability DB 2026-11-17 19:04 UTC and the current Java
DB. Both complete OS/Python scans detected supported Wolfi and finished without
errors or suppressions. The replaced Debian images each had 101 HIGH and 2
CRITICAL findings. Independent evidence checksums are:

- consumer Trivy / SPDX / build metadata:
  `a54166347e36188fa5a62cb1e276a573ec5f770fa558fcef82aa8404c5e7208b`,
  `a9f387549acba463339e610f3bbe65cfbb63ab4c76e1c5ef905c28ea943595b0`,
  `85a5ef48480dfd28904647f52ba59f4cd57558a39c10c8e997534382d0df5a81`;
- anomaly Trivy / SPDX / build metadata:
  `b7f7991701792ce65b6f16e2491a397c38d6b493f344e6e4268ca553c2c00873`,
  `63f3d0fc591b619130cf2ad603baa10332ca982942b9e584fb8e50f5a87deac1`,
  `1ca6a444ed68e63d3f1a247371182adf21116008e864d659c407c5af52d20328`.

These are local image IDs, not registry digests. The images were not published,
signed, or deployed.

## Fresh isolated acceptance

The real consumer, detector and sink applications ran in three disposable
containers on an isolated network with loopback-only ports, read-only roots,
dropped capabilities, `no-new-privileges`, non-root users, and 192--384 MiB
memory limits. SQLite stores used separate test-owned volumes.

- Seven unique sanitized events were persisted; exact replay did not change
  consumer or detector counts.
- Three normal `demo_rule` successes produced no alert.
- Four `kserve` events at a deterministic 0.5 error ratio produced exactly one
  `inference_error_ratio` alert.
- During a test-owned sink outage, four `local_model` events produced one more
  alert. The detector retained one pending outbox row with three attempts.
- Restoring the sink drained the outbox without new traffic. The sink contained
  exactly two alerts; restart retained 11 activity events, two alerts, zero
  pending rows and two sink rows.
- A forced consumer failure returned four HTTP 503 responses and persisted
  nothing, preserving retry semantics.
- Stored events and alerts contained no feature values, API keys, headers,
  private identifiers, or correlation IDs in alerts.
- Observed container memory was 36.69 MiB consumer, 37.85 MiB detector and
  44.03 MiB sink. The disposable database disk peak was not independently
  sampled; all test-owned containers, volumes and network were removed.

The first detector destination used a non-service hostname and correctly failed
closed. Recreating only the test detector with the `.svc` alias recovered its
already committed alert and drained the outbox. No Kubernetes resource changed;
both retained kind clusters remained running.

## Historical versus fresh coverage

The 2026-10-26 evidence remains the real Knative Eventing proof: Eventing 1.23,
Ready Broker/Triggers, Broker delivery, replay, PVC restart persistence, finite
retry and exhausted delivery to the DLQ. Its anomaly run used the older
pre-hardening image. The 2026-11-18 result is fresh exact-image security and
component-level recovery evidence only. No Eventing controller, Broker, Trigger,
channel or DLQ executed in the fresh run.

## Validation

- focused Eventing/anomaly and release checks: 92 passed, 5 skipped;
- full regression: 632 passed, 5 skipped, 87.20% coverage (81% gate passed);
- Ruff: passed; scoped MyPy: no issues in 27 files;
- all nine Knative YAML files / 29 documents parsed;
- immutable production manifest render: passed.

The first full-suite setup put temporary evidence inside the repository and
therefore triggered the expected fail-closed location test. The intended rerun
used a dedicated `/var/tmp` base and passed completely.

## Remaining owner-authorized Knative acceptance

Use a separately owned environment with sufficient measured headroom. Before
mutation, qualify and pin Eventing controller and durable-channel images,
publish/sign the two application images, verify their remote digests and
attestations, provision persistent consumer/detector/sink stores, authenticated
internal delivery, and reviewed NetworkPolicies. Render application manifests
with `scripts/render_production_knative.py`; reject every mutable tag. After
owner authorization, install the compatible Eventing controller and durable
transport, apply the namespace/Broker/Triggers/application manifests, then
repeat normal, anomaly, outage, recovery, restart and exhausted-retry/DLQ tests
while capturing resource identities and logs. Roll back only those explicitly
owned Eventing resources and stores.

C6 remains `BLOCKED`; M10.3 deployment NO-GO and SEC-022 are unchanged.
