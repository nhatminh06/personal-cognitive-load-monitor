# C13 pre-deployment engineering and security qualification

**Date:** 2026-11-18. **Source revision:**
`799d89d6b971237df918bfc2324b4ec0ac22d9b2`.

## Recovered application-image evidence

The exact C5.3 local images remained present. Trivy 0.76.2 used vulnerability
DB 2 updated `2026-11-18T13:03:23Z`. Raw reports are retained under the ignored
`build/c13-security-evidence/raw/` directory; only independently calculated
checksums are tracked here.

| Image | Exact local ID | HIGH / CRITICAL | Trivy JSON SHA-256 | SPDX JSON SHA-256 |
|---|---|---:|---|---|
| FastAPI | `sha256:9609981bd9c775b3937a0d8cf7158c02e786089cd35ce1de5352d90b4ace26c0` | 0 / 0 | `e02d20648f13ddbb36f27ca4fb177f578b3123fc670d1e79f69e8ffab7c25c44` | `260a7d39a05beec39b03ac43783512ee2140fb6d1d4b61e5baa72d59f2a60f51` |
| KServe | `sha256:6e4a0d3c3682fec3c85e3676acb268d422819f5378494f3b26e78ad99cba3f9b` | 0 / 0 | `250a644aba4cab32b951c146734df096554043ee558ba03c1bc343b64d470d1d` | `c3d648dc36152af0808382110923081fc0c4156f3fca023a9751ded61178351e` |

Each scan covered supported Wolfi OS and Python-package targets and reported
one MEDIUM finding. The local OCI IDs and source trees match the C5.3 record;
the historical BuildKit provenance files were not recovered, so the previously
recorded provenance checksums remain historical evidence rather than newly
verified files. No rebuild, signature, attestation or publication occurred.

## Controller ledger progress

The documented KFP 2.17.2 manifests identify the API, persistence-agent and
scheduled-workflow images. The first priority API-server OCI index resolved to
`sha256:8e9f9e66d127fe27f61236bc35a66e8558c58e5f828ad50b15257220140bf023`
and its linux/amd64 manifest to
`sha256:dcae5f50acaecffc2fc2e596fd241db7864627c82089fac4ad92dc4e692bc619`.
A complete fresh scan found **92 HIGH and 3 CRITICAL** findings. The raw report
SHA-256 is `bf72aa5b8fe847bd2d94972da27c52df122bb3c4744640faea4e813c4d35763d`.
The critical findings are Debian `perl-base` CVEs with fixed package versions;
the image also has fixable Go runtime and library findings. The remaining KFP
roles were deliberately not downloaded after this mandatory gate failed.

## Real Kafka and Bronze fixture

The preflight measured 6,875,844,608 available bytes, negligible memory PSI,
125,897,994,240 persistent bytes free and 7,890,448,384 `/tmp` bytes free.
Task-owned Compose services used exact qualified Kafka
`sha256:a90beec03332d23649e3728e53ee13049fcf76564cabdc11ac940baaa0fc0d53`
and SeaweedFS
`sha256:7499507f4f3bcc532fffadc3aaca5f2f5146d998409b9ad5af25d5393813591a`.

The production C8.2 commands generated exactly 65,536 source bytes / 124
records and received 124 all-replica Kafka acknowledgements. Sixteen Bronze
objects contained 72,307 bytes / 124 records and independently read back after
restart with their recorded SHA-256 values. The deterministic Bronze evidence
chain was `0451dd2cb41ae1bbe9d31a3cf41d61f731feb40ad856d9efbe22b023a67dfe1c`.
Peak observed container memory after restart was Kafka 376.8 MiB, SeaweedFS
106.9 MiB and S3 gateway 42.72 MiB.

The post-restart production `--resume` command correctly stopped because live
available memory was 6,296,666,112 bytes, below the 6,442,450,944-byte gate.
Object persistence and checksum readback passed; checkpoint resume execution is
therefore **BLOCKED**, not inferred. All C13 containers, networks and volumes
were removed; both kind clusters were untouched.

## Deployment and durable integration

`scripts/deploy.sh` no longer accepts mutable defaults or mutates immediately.
It now requires exact remote digests, commit/model identity, action-bound owner
authorization, explicit execution authorization and an explicit non-protected
context. It also rejects candidate/unapproved model packages. Deploy verifies signatures, SPDX/SLSA attestations and fresh scans,
uses atomic Helm, waits for API and InferenceService health, supports exact
revision rollback and verified teardown, and writes a sanitized exclusive
evidence record.

For a future KFP runtime, the supported KFP 2.17.2 manifests already select
SeaweedFS as their S3-compatible artifact repository; the locally qualified
SeaweedFS image is the least new machinery, but controller security blocks a
runtime claim. Kafka is the durable Eventing transport choice consistent with
the qualified broker and existing contracts. Knative Kafka controllers/data
plane images remain unqualified, so no Eventing configuration was promoted and
no controller was installed.

Validation completed with 668 passed / 5 skipped tests and 86.95% combined
coverage. Ruff, scoped MyPy (52 files), shell syntax, Helm lint/render,
Terraform formatting and focused release/security tests passed. Terraform
provider-backed validation was **BLOCKED** because Google provider 5.45.2 is
not present in the offline provider cache; no provider download was attempted.
