# Module I final acceptance

This is a source-ready, fail-closed procedure. It does not authorize cloud
creation, model approval, image publication, workflow dispatch, load generation
or teardown. Record a step as runtime verified only after its command succeeds
against the separately approved target.

## Compatibility qualification — BLOCKED

KServe supports distinct Standard and Knative modes. Standard remains the chart
default for Module III. Module I selects
`values.module1-knative.yaml`, which emits
`serving.kserve.io/deploymentMode: Knative`, KPA concurrency autoscaling and
`min-scale: 0`.

The machine-readable decision is [`compatibility-matrix.json`](compatibility-matrix.json).
No candidate is selected. Both maintained KServe `0.20.0` and current `0.21.0`
pin Knative Serving `1.21.1`, Istio `1.27.1` and cert-manager `1.17.0` upstream.
That integration-tested set is unusable for this demonstration:

| Candidate | Integration evidence | Current support/security | Decision |
|---|---|---|---|
| KServe 0.20.0 + Knative 1.21.1 + Istio 1.27.1 + cert-manager 1.17.0 | exact KServe dependency lock | Knative, Istio and upstream cert-manager are EOL; cert-manager supports only Kubernetes through 1.33; Istio 1.27.1 is in published affected ranges | Rejected |
| KServe 0.21.0 + the same dependency set | exact KServe dependency lock | same blockers | Rejected |
| KServe 0.21.0 + Knative 1.23.0 + Istio 1.31.3 + cert-manager 1.21.0 + GKE 1.34.12-gke.1153000 | each component is individually supported; KServe publishes no evidence for the substituted integration | exact images/manifests still need digest inventory and scanning; the GKE patch must be confirmed in `us-central1` | Needs isolated qualification; not deployable |

GKE Regular offers Kubernetes 1.34 and newer, while Knative 1.23 requires at
least Kubernetes 1.34. Version overlap is necessary but does not establish
KServe compatibility. The protected workflow therefore runs
`module1_compatibility.py --require-qualified` before OIDC and fails closed.
Do not mark the matrix `QUALIFIED` until an isolated exact-stack rehearsal
records controller/CRD readiness, effective Revision settings, routing,
scale-to-zero and cold-start inference. Do not use an unpinned installer.

Primary references:

- <https://kserve.github.io/website/docs/install/kserve-install>
- <https://raw.githubusercontent.com/kserve/kserve/v0.20.0/kserve-deps.env>
- <https://raw.githubusercontent.com/kserve/kserve/v0.21.0/kserve-deps.env>
- <https://github.com/kserve/kserve/releases/tag/v0.21.0>
- <https://github.com/knative/community/blob/main/mechanics/RELEASE-SCHEDULE.md>
- <https://cloud.google.com/kubernetes-engine/docs/release-notes-regular>
- <https://istio.io/latest/docs/releases/supported-releases/>
- <https://istio.io/latest/news/security/>
- <https://cert-manager.io/docs/releases/>

The KServe 0.21.0 release publishes SHA-256
`d5bac34adc2e1c41be11892c11040b904af856d683cac358a3ce71afdaa5f294`
for its CRD chart and
`d992919775cf0dbae0e64381d4ccd5da52fde9f18b32e5468c7536508a07bf41`
for its resources chart. Those hashes are release metadata, not a complete
controller inventory or approval to install them.

Concrete unblock options, in preference order:

1. adopt a stable KServe release whose own dependency lock uses supported
   Knative, networking and cert-manager releases, then re-run this review;
2. obtain explicit upstream KServe evidence for the exact substituted candidate;
3. with separate human authorization, qualify the candidate on a disposable,
   isolated Kubernetes 1.34 environment using immutable manifests/images and
   the same custom runtime, then discard it. Record installation, CRD conversion,
   controller readiness, Revision propagation, routing and 1→0→1 inference.

Knative supports multiple networking layers, but CogniFlow does not switch to
Kourier or another provider merely because it supports Knative: KServe's tested
dependency set selects Istio, so any networking substitution is another matrix
that needs equivalent integration evidence.

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

Inventory every Helm chart, CRD bundle and controller image by digest. At
minimum this covers KServe CRDs/resources/controller, Knative Serving
controller/autoscaler/activator/webhook/queue-proxy, the networking
controller/data plane, and cert-manager controller/webhook/cainjector. Scan the
exact images and attach sanitized reports. A version or chart checksum never
substitutes for image digests.

The Knative `config-autoscaler` must explicitly set
`enable-scale-to-zero: "true"`, `stable-window: "60s"` and
`scale-to-zero-grace-period: "30s"`. The stable window smooths the concurrency
signal; only after it is inactive can the 30-second grace period complete the
scale-down. Treat different cluster-wide values as a new reviewed change.

The repository does not install the cloud observability control plane, NGINX,
cert-manager or Knative dependencies. Their exact pinned charts/manifests,
storage classes, retention, controller image digests and ownership must be
approved before deployment; local Compose evidence is not a substitute.

The capacity ledger in `deploy/gke/resource-budget.yaml` reserves 700m CPU and
2 GiB specifically for Knative Serving, networking and autoscaling alongside
the other control planes. Recalculate before adding optional dashboards or
running training concurrently.

## Module I-only cost and operating window

The bounded topology is two `e2-standard-4` nodes in `us-central1` (8 vCPU and
32 GiB total) with 20% system/restart reserve. The October 2026 public-price
basis is approximately `$0.376/hour` before disks, load balancing, storage
operations, logging and traffic. The initial owner-approved window must not
exceed eight hours; use a conservative `$6–$12` envelope. Terraform budget
alerts fire at 25/50/75/90/100% of `$100`, but alerts do **not** stop spend.
Record a calendar expiry and stop on exhausted reserve, an unexpected billable
resource, or any matrix/inventory mismatch.

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
uv run python scripts/module1_compatibility.py \
  --matrix docs/module1/compatibility-matrix.json
uv run dvc status
```

The placeholder render is static validation only and must never be applied.

## Authorized deployment gate

Only after the prerequisites pass, a reviewer may dispatch
`deploy-module1.yaml` from `main` with the two exact signed Artifact Registry
digest references and the approved model lineage. The workflow checks OIDC,
control-plane readiness, signatures and immutable inputs before an atomic Helm
upgrade. It does not approve a model or build an image.

Today dispatch is intentionally blocked by the compatibility gate. After exact
qualification, confirm the requested GKE patch is available in `us-central1`,
review a no-create Terraform plan, verify the protected runner identity, and
inspect Helm inventory including `pending-install`, `pending-upgrade`,
`pending-rollback`, `failed` and `uninstalling`. Any pending state, missing
ownership, context mismatch, or Module III Standard release stops the run.

The workflow first compares the exact Kubernetes context and inspects any
`cognitive-load-monitor` release in `cogniflow`. An existing release must have a
recognized ownership label and matching Standard/Knative mode. Its current
revision and SHA-256 of `helm get manifest` must match the separately entered
approval values. Replacing a Module III `module3-standard` release additionally
requires the protected `replace_existing_release` authorization; otherwise the
workflow stops before Helm can mutate it. Do not create another cluster to
avoid this check.

Standard mode retains the three-second KServe client timeout. Module I alone
sets a bounded 30-second cold-start timeout; NGINX connect/read/send ceilings
are 35 seconds. The protected preflight requires the reviewed Knative global
60-second stable window and 30-second scale-to-zero grace period. The Knative
Revision/request and activator queues must allow at least 35 seconds but remain
finite; this external control-plane setting is a runtime prerequisite, not
installed by this repository.
The workflow also requires Knative `config-defaults` request, response-start
and idle Revision timeouts to equal 35 seconds; missing values and the upstream
300-second/infinite defaults fail closed.

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
   URL, revision and digest-pinned predictor image. Confirm the effective
   Revision carries KPA class, concurrency target `1`, minimum `0` and maximum
   `3`; the protected workflow fails when these annotations do not propagate.
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
  --artifact-root evidence/artifacts \
  --report evidence/module1-report.md \
  --require-cloud-acceptance
```

Each check must reference a distinct, relative, non-symlink JSON artifact below
the artifact root and declare its SHA-256. The validator rejects missing,
changed, duplicate, oversized, escaping or secret-bearing artifacts. Schema
validation and checksum verification establish bundle integrity only: status
strings are self-declared and the generated report always says independent
runtime review is required. A human reviewer must compare the sanitized
artifacts to the exact cluster, namespace, commit, model and image identities
before acceptance. Never record credentials or private environment values.

The report is created once with mode `0600`; existing reports are never
overwritten. A failed gate remains `blocked`—never rewritten as verified.

Use `helm history` only for diagnosis. A rollback must name
`cognitive-load-monitor`, namespace `cogniflow`, and the exact revision and
manifest identity approved during the pre-deployment inspection; never target
another release or an unreviewed revision. Teardown is a different owner-approved operation: first export
non-secret evidence and costs, then review retained GCS objects/PostgreSQL
backups, load balancers, addresses, NAT and deletion protection. Never run
Terraform destroy or delete retained data as part of acceptance.
