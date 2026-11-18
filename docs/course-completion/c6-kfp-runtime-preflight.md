# C6 real KFP execution and model qualification

**Date:** 2026-11-17

**Starting revision:** `ae9b09180149210fcf0160d686d079347b16e7be`

**Decision:** **BLOCKED — no authorized, secure KFP runtime is available**

No Kubernetes resource, Docker object, MLflow record, model approval, registry,
or cloud resource was changed. No pipeline run was submitted. The two retained
kind clusters remained running and untouched. C5.9, M10.3 deployment NO-GO, and
SEC-022 are unchanged.

## Runtime and resource evidence

Read-only inspection used the independently qualified kubectl
`v1.35.10-cogniflow.1`, SHA-256
`130b354df841e743ee6a5580d1cdb09844ba0a0d4538a6b39c508c1526b516ef`.

- `cogniflow-local` and `cogniflow-module1-qualification` were the only kind
  clusters. Neither contained a KFP/Argo Workflow CRD, KFP service, MLflow
  service, or pipeline controller.
- The host had 16,469,766,144 bytes physical RAM and 4,443,127,808 bytes
  initially available. Swap usage was 10,438,717,440 bytes. `/tmp` had only
  225,505,280 bytes available initially and 82,784,256 bytes after validation.
  The persistent filesystem retained approximately 127 GB available.
- This fails the existing 6 GiB local-start gate. The repository budget also
  assigns 8–12 GiB to the KFP/KServe/Knative controller tier before workload
  headroom. Installing KFP beside both retained clusters was therefore neither
  authorized nor resource-safe.

## Pipeline contract and component image

The current graph compiles with KFP SDK `2.17.3` to six container components
plus three artifact importers. The components remain ordered as validate,
prepare, train, evaluate/select, register, and provenance. All six use one
immutable image parameter, disable caching, request 250m CPU/512 MiB, limit one
CPU/2 GiB, run as UID/GID 10001, and have a 600-second timeout.

The current compile-only package SHA-256 is
`386a49896b9062c3f10c53ee3c3b7de0aa24eb7f2d8f6948e0fb85ade9d52f74`.
It embeds the retained historical component identity only to exercise static
compilation; it is not executable C6 evidence.

The sole retained component image is
`localhost:5001/cogniflow-kfp@sha256:8cd171d9d71610e0a29469d86f94caa638662e201563a038d2db06976c43a614`.
Its former loopback registry no longer exists and the image declares
`COGNIFLOW_CODE_REVISION=26bbc3fdbbeb40e41167e73e5726dbcefe05b7a0`, not the
C6 revision. Input validation would reject that mismatch before preparation.
Its historical Trivy 0.67.2 result asserted zero *fixable* HIGH/CRITICAL
findings, which does not satisfy the current complete zero-HIGH/zero-CRITICAL
gate. No current component SBOM, signature, provenance attestation, or complete
scan was available. Submission stopped before workloads as required.

The historical backend was KFP manifests `2.17.2` with SDK `2.17.3`. Its
October run IDs and component image remain historical evidence only; they were
not reused or presented as C6 execution.

## Independently reverified reference candidate

`scripts/qualify_local_candidate.py` returned
`PASS_LOCAL_CANDIDATE_ONLY` for the retained reference candidate. The generated
review packet SHA-256 was
`124d5feec90fc773b77d8e0a8fea605aa8f89c0d359eaa3b4462182020280d89`.

| Identity | Reverified value |
|---|---|
| Candidate | `cogniflow-c22-independent-20261117/1` |
| Local MLflow run | `cfe2e543f44043138e5b236e5f2115b5` |
| Dataset SHA-256 | `9ff25b2b325579c7142202436e870886eb0c76a110e0e36e3bb50fc197621a48` |
| Split SHA-256 | `6a43e788f297a1c17e3ece4d57e587c103d093381308b1f282b63b38ce0edc2c` |
| Model skops SHA-256 | `0861a20d77f9229d832a0145ebb28e56dae3b650a78eec2229e56dfa1a3a1c19` |
| Artifact-tree SHA-256 | `ed5be0c48c11a0d5315d43cc768df493e3839e09b07f3deaf7c9bddab6138197` |
| Selected model | Logistic regression |
| Approval | `candidate`; production packaging rejected it |

The explicit grouping key is the SHA-256 of the canonical six-feature vector.
Train/validation/test contain 36/12/12 groups and 125/43/42 rows. Class counts
are train LOW 41, MEDIUM 41, HIGH 43; validation LOW 14, MEDIUM 15, HIGH 14;
test LOW 15, MEDIUM 14, HIGH 13. Validation and test each have zero feature
groups overlapping training.

The predeclared selection rule maximizes validation macro-F1, then validation
accuracy, then prefers dummy majority, logistic regression, and random forest
in that order. Validation results were:

- majority: accuracy `0.32558139534883723`, macro-F1
  `0.16374269005847952`;
- logistic regression: accuracy `1.0`, macro-F1 `1.0`;
- random forest: accuracy `1.0`, macro-F1 `1.0`.

The tie rule selected logistic regression. Its untouched final test returned
accuracy `1.0` and macro-F1 `1.0`. These are synthetic-proxy metrics, not
clinical, medical, psychological, or real-world cognitive-load validation.

This local MLflow identity is not a KFP result. C6 produced no KFP run ID, no
new MLflow run, no registered version, and no owner-reviewable KFP approval
packet. The candidate remains unapproved and undeployed.

## Validation

- Full regression: 632 passed, 2 skipped, 5 warnings in 74.40 seconds.
- Combined coverage: 87.20%, above the 81% gate.
- Ruff: passed for `src`, `scripts`, and `pipelines`.
- Scoped MyPy: passed for 27 API/data/eventing/anomaly files.
- Current KFP compilation: passed; nine DAG tasks, KFP SDK 2.17.3.
- Independent local candidate retrieval, digest, split, load/reload, corrupt
  artifact, and unapproved packaging checks: passed.
- Graphify deterministic source extraction: 2,412 nodes and 6,368 edges.
  Documentation semantics were not generated; optional Terraform and SQL
  parsers were unavailable, so those graph portions are incomplete.

## Exact unblock requirements

The owner must separately authorize an isolated KFP runtime or an already
running qualified endpoint, without modifying either retained cluster. Before
submission it needs:

1. enough measured headroom for the pinned KFP 2.17.x backend, artifact store,
   one-replica MLflow registry, and the sequential 512 MiB-request/2 GiB-limit
   tasks;
2. a component image built from the exact reviewed Git revision, published by
   remote immutable digest, with SBOM/provenance/signature and a current complete
   0 HIGH/0 CRITICAL scan;
3. digest-pinned backend/controller images, compatible Kubernetes, isolated
   namespace/service account, NetworkPolicies, PVC/object storage, and verified
   MLflow reachability;
4. immutable copies of the three synthetic inputs with independently checked
   digests; and
5. explicit authorization to submit one positive run and one corrupted-input
   negative run and retain their sanitized logs/artifacts.

Only then may C6 record a new KFP run ID, independently retrieve the registered
candidate, compare its metrics and digests to C2.2, and prepare an owner review
packet. A successful run must still leave `approval_status=candidate`.
