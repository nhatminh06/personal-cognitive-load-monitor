# Module III: training and serving

## Training and metadata

The compiled KFP v2 pipeline has six tasks: validate history, prepare the dataset,
train candidates, evaluate/select, register the candidate and record provenance.
KFP uses Argo Workflows, MySQL for pipeline state, ML Metadata for lineage,
SeaweedFS for local artifacts and MLflow for experiments and model registration.
The 15 local release identities are recorded in
`deploy/releases/kfp-local-images.json`.

Historical isolated KFP evidence from 2026-10-26 includes positive run
`cee7540f-9c9e-4078-a9d7-c61c4c4bd9fc` and lineage-negative run
`5143c5ae-9c98-4c4d-9f21-f5647ec63cf9`. This is local evidence, not GKE proof.

## Approval and serving

Candidate registration is not model approval. Packaging validates the selected
MLflow identity, dataset and artifact-tree hashes, trusted skops types and an
explicit approval record. KServe uses the packaged immutable model only after that
gate. FastAPI validates served model provenance and fails readiness closed on a
mismatch or unreachable predictor.

Knative Eventing emits sanitized CloudEvents to a persistent consumer. The anomaly
service evaluates deterministic event-time rules, persists state and delivers
deduplicated alerts through an outbox. Historical local Broker/Trigger evidence is
dated 2026-10-26; hardened anomaly recovery is regression-tested but not freshly
deployed to Knative.

## Current blockers

- No model is approved for production deployment.
- Images are locally qualified but unpublished, unsigned and unattested remotely.
- GCS Workload Identity and artifact-generation checks require an authorized GKE
  runtime.
- KServe, Knative and the complete platform have not been deployed to GKE.
- The Spark SEC-022 image is excluded from Kubernetes and GKE.

See [deployment](deployment.md), [security](security.md) and [evidence](evidence.md).
