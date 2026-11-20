# Security

## Boundaries

- API and runner credentials come from runtime Secrets or private environment
  files; they are not committed or printed.
- CI is read-only and cannot publish, authenticate to cloud providers or deploy.
- Containers use non-root users, dropped capabilities, read-only roots and bounded
  writable volumes where supported.
- Production images require immutable registry digests, signatures, attestations,
  SBOMs and an unsuppressed 0 HIGH / 0 CRITICAL scan.
- Model packaging verifies dataset, model and artifact-tree hashes plus trusted
  serialization types. Candidate registration never implies approval.
- Event storage verifies canonical content hashes and rejects conflicting replay.

## Open decisions

SEC-022 permits the exact Spark dependency image only for isolated local
development. It is forbidden in Kubernetes, GKE and production. The signed
[exception](security-audit/sec-022-development-exception-proposal.md) and
[owner packet](security-audit/sec-022-owner-decision-packet.md) remain authoritative.

SeaweedFS has passed S3 compatibility checks, but equivalence to an explicit MinIO
course requirement is unresolved. Cloud IAM, Workload Identity, Secret Manager,
TLS/DNS, registry policy and runtime NetworkPolicy require authorized validation.

## Qualified release tooling

The rebuilt kubectl v1.35.10 candidate has SHA-256
`130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef`
and passed its local 0 HIGH/CRITICAL gate. The deployment runner subsequently
passed whole-image and network-disabled runtime qualification. Detailed immutable
records are retained in
[kubectl qualification](security-audit/c54-kubectl-qualification.md) and
[runner qualification](security-audit/c58-final-runner-qualification.md).

Local qualification does not authorize publication or deployment. Re-scan the
published exact registry manifest and verify its signature and attestations.
