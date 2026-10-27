# Module I final acceptance

This is a source-ready, fail-closed procedure. It does not authorize cloud
creation, model approval, image publication, workflow dispatch, load generation
or teardown. Record a step as runtime verified only after its command succeeds
against the separately approved target.

## Compatibility decision and blocker

KServe `v0.20.0` supports distinct Standard and Knative modes. Standard remains
the chart default for Module III. Module I selects
`values.module1-knative.yaml`, which emits
`serving.kserve.io/deploymentMode: Knative`, KPA concurrency autoscaling and
`min-scale: 0`.

The repository targets GKE/Kubernetes `1.34`. KServe 0.20's own dependency file
pins Knative Serving `1.21.1`, cert-manager `1.17.0` and Istio `1.27.1`.
Knative 1.21 is now outside community support; supported Knative 1.23 requires
Kubernetes 1.34, but this repository has not qualified KServe 0.20 against that
newer Serving release. Therefore installation is **blocked** until an owner
selects and security-reviews one exact supported matrix, image digests and
manifests. Do not use an unpinned quick-install script.

Primary references:

- <https://kserve.github.io/website/docs/install/kserve-install>
- <https://raw.githubusercontent.com/kserve/kserve/v0.20.0/kserve-deps.env>
- <https://github.com/knative/community/blob/main/mechanics/RELEASE-SCHEDULE.md>
- <https://cert-manager.io/docs/releases/>

## Required GCP and GitHub prerequisites

Before any authorized run, independently confirm:

1. an owner-approved billing account, budget, fixed runner `/32`, Terraform
   plan and protected remote-state remediation;
2. the private GKE 1.34 context and cluster UID, two bounded `e2-standard-4`
   nodes, `metrics.k8s.io/v1beta1` availability, Dataplane V2 and Workload Identity;
3. reviewed KServe, Knative Serving/networking and cert-manager versions and
   immutable controller image IDs;
4. `module1-production` GitHub environment with required reviewers, main-only
   policy and a protected `cogniflow-gke-deploy` runner;
5. OIDC provider and deployer account from Terraform—never a JSON key;
6. Artifact Registry digest references whose Cosign identity, provenance, SBOM
   and exact-image Trivy reports passed the protected release workflow;
7. externally created API and NGINX authentication Secrets, a real DNS name,
   valid TLS issuer/certificate and no public backend Service;
8. separately approved MLflow model name/version/artifact digest and matching
   model, dataset and feature-schema digests;
9. PostgreSQL registry metadata backup/PITR and tested restore plan; GCS remains
   artifact storage, not registry metadata;
10. namespace Pod Security, RBAC, quotas, NetworkPolicies, logging retention,
    rollback owner and teardown owner.

The repository does not install the cloud observability control plane, NGINX,
cert-manager or Knative dependencies. Their exact pinned charts/manifests,
storage classes, retention, controller image digests and ownership must be
approved before deployment; local Compose evidence is not a substitute.

The capacity ledger in `deploy/gke/resource-budget.yaml` reserves 700m CPU and
2 GiB specifically for Knative Serving, networking and autoscaling alongside
the other control planes. Recalculate before adding optional dashboards or
running training concurrently.

## Offline source gate

```bash
uv run ruff check src scripts
uv run pytest src/tests --cov=src/preprocessing_api --cov=src/cogniflow_data \
  --cov=src/cogniflow_eventing --cov=src/cogniflow_anomaly \
  --cov=src/cogniflow_kserve --cov-fail-under=81
uv run mypy --explicit-package-bases src/preprocessing_api src/cogniflow_data \
  src/cogniflow_eventing src/cogniflow_anomaly src/cogniflow_kserve \
  scripts/module1_acceptance.py --ignore-missing-imports
helm lint helm/cognitive-load-monitor
helm template module1 helm/cognitive-load-monitor --namespace cogniflow \
  -f helm/cognitive-load-monitor/values.gke.yaml \
  -f helm/cognitive-load-monitor/values.module1-knative.yaml \
  --set-string image.digest=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --set-string kserve.image.digest=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
  --set-string config.modelName=cognitive-load-classifier \
  --set-string config.modelVersion=1 \
  --set-string config.modelSha256=cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
  --set-string config.modelArtifactSha256=dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd \
  --set-string config.modelDatasetSha256=eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee \
  >/tmp/cogniflow-module1-render.yaml
terraform -chdir=infra/terraform/gke fmt -check
uv run dvc status
```

The placeholder render is static validation only and must never be applied.

## Authorized deployment gate

Only after the prerequisites pass, a reviewer may dispatch
`deploy-module1.yaml` from `main` with the two exact signed Artifact Registry
digest references and the approved model lineage. The workflow checks OIDC,
control-plane readiness, signatures and immutable inputs before an atomic Helm
upgrade. It does not approve a model or build an image.

Immediately record identity before testing:

```bash
kubectl config current-context
kubectl get namespace cogniflow -o jsonpath='{.metadata.uid}{"\n"}'
kubectl get nodes -o wide
helm status cognitive-load-monitor -n cogniflow -o json
kubectl get inferenceservice cognitive-load-classifier -n cogniflow -o json
kubectl get hpa cognitive-load-monitor -n cogniflow -o json
```

Stop if context, namespace UID, release revision, images or model provenance do
not match the approved change record.

## Independent KServe scale-to-zero acceptance

1. Wait for `InferenceService` condition `Ready=True`; capture the condition,
   URL, revision and digest-pinned predictor image.
2. Send one authenticated six-feature request through FastAPI. Capture only
   status, response contract, trace ID and `/model-info`; confirm exact approved
   model/version/artifact/dataset digests and `is_fallback=false`.
3. Record predictor/activator replica counts once every 15 seconds. Stop sending
   traffic and wait only for the reviewed scale-to-zero timeout. Prove predictor
   replicas reach exactly zero.
4. Send one new authenticated request. Prove replicas rise above zero and a
   correct prediction returns after the measured cold start.
5. Make the backend unavailable in the approved failure window and prove the
   API returns 5xx; it must never return `demo_rule`.

KServe and HPA observations are separate. API HPA replicas do not prove model
scale-to-zero.

## Independent bounded HPA acceptance

Metrics Server must return `kubectl top pods -n cogniflow` before load starts.
Record initial HPA conditions and replica count. Use at most 10 authenticated
requests/second for at most 120 seconds, with a client timeout and a human stop
switch. Record HPA state every 15 seconds, healthy responses during scaling and
the peak replica count; it must not exceed the configured maximum of five.
Stop load, then prove replicas return to the configured minimum of two within
the reviewed stabilization window. Abort on elevated errors, pending pods,
resource pressure or unexpected cost.

## Gateway and observability acceptance

Record NGINX controller readiness, certificate subject/issuer/expiry and public
Ingress address. An unauthenticated request must return `401`; an authenticated
request must return `200`. The API and predictor Services must remain
`ClusterIP`, and direct public access must fail.

For the same request, record Prometheus target and bounded request/prediction
metrics, Grafana dashboard UID, API trace ID and matching Tempo trace, sanitized
JSON request log and matching Loki query. Run read-only `dvc status`, record the
Evidently report SHA-256/path and both dataset digests. Never record credentials
or raw request data.

## Evidence, rollback and teardown

Populate a JSON file conforming to `evidence-schema.json`, then validate it:

```bash
uv run python scripts/module1_acceptance.py evidence/module1.json \
  --expected-context EXPECTED_GKE_CONTEXT \
  --report evidence/module1-report.md \
  --require-cloud-acceptance
```

The report is created once with mode `0600`; existing reports are never
overwritten. A failed gate remains `blocked` with its evidence link—never
rewritten as verified.

Use `helm history` and the previously verified digest for a scoped Helm
rollback. Teardown is a different owner-approved operation: first export
non-secret evidence and costs, then review retained GCS objects/PostgreSQL
backups, load balancers, addresses, NAT and deletion protection. Never run
Terraform destroy or delete retained data as part of acceptance.
