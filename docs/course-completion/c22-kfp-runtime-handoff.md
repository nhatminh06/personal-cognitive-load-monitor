# C22 metadata writer and KFP runtime handoff

**Date:** 2026-11-19

**Starting revision:** `a234676e8dd8cc43dcd5802110cd02b5d6c78e5e`

**Decision:** **PARTIAL — all headless service images qualify locally; real workflow remains blocked**

## Metadata writer qualification

The C21 build used `wget` even though source retrieval is a Docker build
operation. C22 replaces it with Dockerfile-native `ADD --checksum` for exact KFP
source commit `7dd28116ad652bfb7b6c282e7920be84e6a7634a`, archive SHA-256
`4b50a172728854115776532673e0df6d98679fb8303a806d901bb7825e359e55`.
No download utility or unrelated runtime dependency was added.

The resulting non-root image is
`sha256:c2a8d2322156040087818323c1e5d1e685dbb63142f52bad263512fb00fa2ae1`.
Its complete Wolfi and Python inventories contain 34 OS packages and 33 Python
distributions. Trivy 0.76.2 reported 0 HIGH and 0 CRITICAL findings without
suppressions. The scan SHA-256 is
`d946273b0c12aaf101c2a1e2e1884b325edbfc94964f9de2698123ddd473f78d`;
the SPDX SHA-256 is
`b57412d59a829b0fd15d11523cca22e7292fd38f196aee396ca4f3537c1d0470`.
BuildKit emitted only local provenance; no remote signature or attestation is
claimed.

The exact upstream writer source hashes match C21's verified KFP archive. Its
entrypoint is `/venv/bin/python -u /kfp/metadata_writer/metadata_writer.py` as
UID/GID 65532. The upstream metadata-helper suite passed 11/11. With networking
disabled and no service account, the real entrypoint rejected the missing
Kubernetes context cleanly with exit 1. Actual Pod/Argo publication remains
BLOCKED until an authorized KFP workflow exists; it was not simulated.

## MLMD invalid-credential defect

The C21 exit code 139 reproduces as signal 11 (SIGSEGV), not a graceful
authentication failure. Against a fresh task-owned `metadb`, table count stayed
zero before and after, the invalid client never authenticated, the container
was not OOM-killed, and no supplied test password appeared in captured logs.
This is an upstream MLMD 1.14 correctness defect after `mysql_real_connect`
fails. No binary patch was attempted because the crash cause inside the
upstream native binary is not established. Kubernetes restart policy can
contain availability impact but does not make the crash acceptable behavior.

## Headless overlay

The writer patch pins its exact local identity, directs it to
`metadata-grpc-service:8080`, retains the upstream least-privilege ServiceAccount
and Role, runs with a read-only filesystem, drops all capabilities, bounds `/tmp`
to 64 MiB, and sets 25m/128Mi requests with 500m/512Mi limits.

The retained exact KFP 2.18.1/Argo 4.1.6 base renders to 73 objects. All 16
container and init-container references are immutable digests; structural
Kubernetes 1.34 OpenAPI validation reports zero errors. Render SHA-256 is
`6dc13b9fedfb4f8b528f87a5f6be33175bf1a9f29c11c1bf95d279b100f13322`.
No manifest was applied.

## First owner-authorized KFP workflow

This procedure extends the existing C11/C10 acceptance path; it does not create
a second orchestrator. Perform it only on an isolated, explicitly authorized
target matching `cogniflow-c11-*`, with at least 12 GiB available memory and 60
GiB free disk.

1. Build a dedicated training-component image from the current commit and pass
   the zero-HIGH/zero-CRITICAL gate. The retained combined image
   `sha256:8cd171d9…3a614` has 60 HIGH findings and is prohibited.
2. Publish every qualified byte-identical image, including the new writer and
   training component. Resolve remote manifest digests, sign them, attach SPDX
   and SLSA attestations, and freshly scan those remote digests.
3. Put all required roles into the existing C11 image ledger, including
   `kfp-metadata-writer` and `cogniflow-kfp`. Set the exact controller matrix,
   explicit kubeconfig, qualified kubectl/Cosign/Trivy paths and owner approval
   in the C11 plan, then run:

   ```sh
   scripts/run_c11_acceptance.sh /secure/c22-plan.json /secure/c22-preflight
   ```

   Continue only if the preflight exits zero and records
   `mutation_executed: false`.
4. Create a release overlay outside Git that replaces every local repository
   name in `infra/kfp-local/` with the corresponding verified remote digest.
   Render it and require zero mutable image references and the same 73-object
   schema-valid contract.
5. Prepare mode-0600 input files for `cogniflow-mysql` (`username`, `password`,
   `root-password`) and `mlpipeline-minio-artifact` (`accesskey`, `secretkey`).
   Create those Secrets only after authorization; never place values on the
   command line or in Git.
6. Apply the reviewed release overlay with the qualified kubectl's explicit
   `--kubeconfig` and `--context`. Wait for MySQL, SeaweedFS, MLMD, MLflow, KFP
   API, persistence agent, scheduler, writer and Argo controller availability.
   Verify MLMD schema 10, empty candidate registry, durable PVCs and S3 bucket.
7. Compile `pipelines.cogniflow_training_pipeline.build_pipeline()` with the
   verified remote training-component digest. Use the actual synthetic feature,
   label and manifest S3 URIs, current Git SHA, fixed training cutoff and
   `http://cogniflow-kfp-mlflow.kubeflow.svc:5000`.
8. Port-forward only the KFP API to loopback and submit with
   `kfp.Client(host=...).create_run_from_pipeline_package(...)`. Save the
   returned `run_id`; never substitute a local MLflow ID. Wait for terminal
   success and export the run JSON, workflow YAML and logs.
9. Independently query MLMD for the run context/executions/artifacts/events,
   MLflow for the exact run and unapproved model version, and SeaweedFS for the
   registered model bytes. Recompute dataset, artifact and artifact-tree
   SHA-256 values and reconcile them with component output and provenance.
10. Submit a second run with a deliberately invalid manifest digest. Require
    failure before training, no model version, no orphan live artifact, and no
    silent fallback. Restart MLMD/MLflow/SeaweedFS individually and repeat
    readback. Export all evidence through the existing C10 report validator.
11. Roll back only the exact release-overlay resources if acceptance fails.
    Preserve evidence and PVCs until owner review; delete them only under a
    separate explicit cleanup authorization.

Required owner authorizations are: isolated-cluster mutation, remote registry
publication/signing, deployment of the reviewed remote digests, creation of the
two named Secrets, two KFP submissions and exact-resource rollback. Model
approval is neither required nor authorized—the result remains a candidate.

The machine-readable [assessment](c22-evidence/assessment.json) records exact
identities and blockers.
