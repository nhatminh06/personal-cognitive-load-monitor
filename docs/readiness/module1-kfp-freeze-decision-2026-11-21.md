# Module I KFP freeze decision — 2026-11-21

**Decision: `FROZEN — DEFER_KFP / NO-GO`.** M1-KFP4 is the final preparation milestone. Its verified offline improvements are preserved, but they do not authorize Docker, Kubernetes, deployment, or another KFP preparation cycle.

## Preserved closure

- KFP 2.18.1 and Argo Workflows 4.1.6 source identities were recovered.
- The complete local recursive source graph rendered reproducibly to 73 objects. Both M1-KFP4 renders and the M1-KFP3 patched render have SHA-256 `060e410a8240bd60acee65014baa6152d7e0793647a5ddc9e8c6cdbd172cf7a0`.
- KFP API server, persistence agent, SeaweedFS, and Argo workflow controller have explicit CPU and memory budgets.
- The release ledger separates the active local S3 MLflow digest from the retained cloud GCS MLflow digest; security evidence remains digest-specific.
- Workflow accounting covers the training main container, KFP driver/importer/launcher, control-plane steady state, configured replacement surge, reserves, and PVCs.
- Historical validation remains scoped as recorded: M1-KFP3 had 709 passed, 2 skipped, 87% coverage; M1-KFP4 focused validation had 59 passed. Neither result was rerun or relabeled here.

## Unresolved blockers

| Blocker | Status |
|---|---|
| Fresh Argo archive checksum differs from retained C16 archive | FAIL |
| Fresh Argo commit signature verification lacks the public key | UNVERIFIED |
| Exact MySQL image security qualification | INCOMPLETE |
| MLMD invalid-credential SIGSEGV root cause | UNRESOLVED |
| Complete MLMD image runtime availability; one required compressed layer was absent offline | UNVERIFIED |
| 12 GiB available-memory start gate | FAIL; M1-KFP4 recorded about 1,031 MiB short |
| Argo init/wait executor CPU and memory resources | UNBOUNDED / UNVERIFIED |
| Nine workflow `emptyDir` volumes per execution pod | UNBOUNDED / UNVERIFIED |
| Complete workflow capacity and Kubernetes runtime suitability | UNVERIFIED |
| Release provenance and deployment authorization | INCOMPLETE / NOT AUTHORIZED |

Stale on-disk or historical runtime evidence cannot close these gates. The retained reports and evidence are not rewritten by this freeze.

## Resume criteria

Resume KFP only through an owner-authorized runtime milestone after all of the following are true: the 12 GiB host gate passes without disturbing retained resources; exact required image content and security evidence are available; MySQL and MLMD gates are resolved; executor and ephemeral-storage budgets have defensible measurements; source provenance gaps have an accepted disposition; and an isolated disposable environment plus deployment authority are explicitly granted. A resume must test actual workflow topology, failure/retry overlap, storage peaks, MLMD behavior, and end-to-end capacity.

Until then, `DEFER_KFP` remains in force. Do not create M1-KFP5, start Docker/Kubernetes, or resume the MLMD diagnostic from this decision.

## This milestone

No KFP tests were repeated and no KFP source or manifest was changed. The only KFP artifact added is this decision record; checksummed review evidence is retained under ignored `build/security-scans/kfp-freeze-spark-remediation-2026-11-21/`.
