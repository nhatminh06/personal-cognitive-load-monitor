# M10.1 security remediation and offline qualification

**Decision:** Offline source gates exercised here are `PASS_OFFLINE`, but
deployment remains **NO-GO**. The deployment runner is `BLOCKED`, Kubernetes
schema validation is `NOT_RUN`, runner bootstrap is `NEEDS_RUNTIME`, and the
Gateway remains `GATEWAY_RUNTIME_UNVERIFIED` / `NEEDS_RUNTIME`.

## Source and scope

- Starting source: `a914474c2f5c6606cf6e06034306be4268003cfc`
- Published ancestor: `b7f3ddef1d30eb52e80887d27445c5724a198ce3`
- Branch: `feat/m10-1-security`
- Final commit: the commit containing this report; the exact SHA is recorded in
  the local handoff because a commit cannot contain its own identity.
- Scope: sanitized public source only. No ignored state, Track B evidence,
  credentials, downloaded binaries, cloud calls, deployment, push, or image
  publication entered the change.

## Changed files

- `deploy/gke/ephemeral-runners.yaml`
- `deploy/gke/runners/Dockerfile.deploy`
- `deploy/gke/runners/README.md`
- `deploy/gke/runners/deploy-inputs.SHA256SUMS.example`
- `docs/cloud-deployment.md`
- `docs/m10-1-security-remediation.md`
- `helm/cognitive-load-monitor/templates/networkpolicy.yaml`
- `helm/cognitive-load-monitor/values.gke.yaml`
- `helm/cognitive-load-monitor/values.yaml`
- `infra/terraform/gke/tests/inputs.tftest.hcl`
- `src/tests/test_gke_cloud_readiness.py`
- `src/tests/test_m10_release_security.py`

## Runner Pod correction

Before M10.1, both runner containers had writable root filesystems. Trivy 0.76.2
reported two HIGH `KSV-0014` findings. Each Pod was already non-root, dropped
all capabilities, disabled privilege escalation and service-account token
mounting, and used no privileged container, host Docker socket, or `hostPath`.

After M10.1, an uncredentialed init container copies the required immutable
runner payload from `/home/runner` into a bounded writable `emptyDir`. The main
container runs from `/runner` with `readOnlyRootFilesystem: true`. Separate
size-limited volumes back runner home, `_work`, `_temp`, and `_tool`; pod UID,
GID and `fsGroup` remain 1001 with `OnRootMismatch`. The registration token is
available only to the main container through its Secret reference.

The repeated Trivy configuration gate reports zero findings for
`ephemeral-runners.yaml` and zero HIGH/CRITICAL findings across all eight GKE
configuration targets. This is `PASS_OFFLINE`; exact-image runner registration,
job execution, cancellation, cleanup and volume sizing remain `NEEDS_RUNTIME`.

## Deployment-runner supply chain

The historical exact candidate remains `BLOCKED`: **13 HIGH, 0 CRITICAL**.
The restored 13-row matrix in the runner README identifies two Ubuntu package
occurrences, the Actions Runner embedded .NET dependency, Cosign, Helm and
seven kubectl embedded dependency/runtime occurrences. Fixed dependency
versions are recorded only where the historical scanner established them;
replacement release artifacts remain `UNVERIFIED`.

`Dockerfile.deploy` is a minimal fail-closed build scaffold. It pins the base
digest, requires a preverified local Linux/amd64 artifact context, rechecks an
owner-supplied checksum manifest, removes Docker/containerd/runc/sudo and runs
as UID/GID 1001. Its example checksum manifest intentionally contains invalid
`UNVERIFIED` tokens. It cannot be treated as an accepted candidate until the
owner independently verifies compatible official artifacts.

No exact deployment-runner image was built or scanned. Status is `NOT_RUN`,
not `PASS_EXACT_IMAGE`. Cached local images with unproven provenance were
explicitly rejected as substitutes.

## Kubernetes schemas and controller resources

Helm lint and GKE rendering pass. The rendered Service is `ClusterIP`, all
application images are digest-bound, and no Ingress, Gateway, HTTPRoute,
LoadBalancer, NodePort, public CIDR, or mutable production image is introduced.
Static regressions cover runner Pods, NetworkPolicies, ServiceAccounts,
ResourceQuotas, storage controls, KServe/Knative source resources and the
fail-closed external route.

No verified kubeconform/kubeval executable or pinned Kubernetes 1.35 core plus
KServe, Knative, monitoring and Gateway CRD schema bundle is present. Genuine
schema validation is therefore `NOT_RUN`; YAML parsing, Helm rendering and
Trivy configuration checks are not mislabeled as schema qualification.

## Terraform offline qualification

Terraform 1.15.9 initialized with `-backend=false`, `-lockfile=readonly`, a
disposable `TF_DATA_DIR`, and locally cached Google provider 5.45.2. No state,
credentials, backend, plan against GCP, or cloud API was used. `terraform
validate` passed. Seven mock-provider tests passed for the valid bounded input
set and rejection of a placeholder project, other region, duplicate zones,
nonnumeric project number, absent budget channel, and public control-plane
range. Static tests retain the private-cluster, WIF, IAM, GAR/GCS, budget,
storage, deletion and teardown controls.

The plugin-dir installation was reported by Terraform as `unauthenticated`.
Its version is exact and lock-selected, but independent signed-package
provenance was not reconstructed. Provider-backed syntax validation is
`PASS_OFFLINE`; provider artifact provenance remains a prerequisite for any
release evidence and all cloud planning remains `NEEDS_OWNER_APPROVAL`.

## Gateway and ingress

GKE ingress remains disabled and no replacement Gateway is created. The API
NetworkPolicy now omits the otherwise unused `gke-managed-system` ingress
allowance unless `networkPolicy.externalIngressEnabled` is explicitly enabled;
GKE values keep it false. This closes an unnecessary source namespace path
without claiming Gateway functionality.

TLS termination, managed certificates, IAP/authentication, Cloud Armor, health
checks, route ownership, static IP/DNS, backend isolation and live default-deny
behavior still require an authorized disposable cluster. Status remains
`GATEWAY_RUNTIME_UNVERIFIED` / `NEEDS_RUNTIME`.

## Validation record

Tool versions: Python 3.11.17, Pytest 9.1.1, coverage 7.17.0, Ruff 0.15.17,
Helm 4.3.0, Terraform 1.15.9, Trivy 0.76.2, Actionlint source module 1.7.12,
Gitleaks 8.30.0, Docker 29.9.1. Actionlint and Gitleaks were built offline from
the existing Go checksum-verified module cache. Trivy used cached check bundle
`sha256:0491169789b867ae5a7353381220c1d4d97b3a0d6d9dfd84a25d06f0ba68aa93`;
its vulnerability database is dated 2026-10-25 and is not current image-scan
evidence.

Results:

- Focused M10.1/GKE regressions: 32 passed.
- Full Python/coverage: 601 passed, 2 skipped, 5 warnings; 87.13%, exceeding 81%.
- Ruff: passed.
- Helm lint: one chart passed; GKE render passed.
- Terraform format, init/validate and tests: passed; 7 Terraform tests passed.
- Trivy GKE config gate: 8 targets, zero HIGH/CRITICAL findings.
- Actionlint: passed.
- Gitleaks sanitized tree and exact commit range: recorded after final commit.
- Kubernetes schemas: `NOT_RUN`.
- Exact deployment-runner build/scan: `NOT_RUN`; historical 13 HIGH / 0 CRITICAL remains `BLOCKED`.

## Privacy, licensing and readiness

The diff adds no dependency, vendored executable, dataset, personal record,
credential, private evidence, generated scan dump, or third-party source. The
Dockerfile references existing upstream components but does not redistribute
them; existing `LICENSE` and `THIRD_PARTY_NOTICES.md` remain unchanged. The
sanitized publication boundary is preserved.

Overall readiness is **NO-GO**. The next milestone is an owner-prepared offline
artifact qualification: verify compatible deployment-tool artifacts and the
locked Terraform provider package, obtain pinned Kubernetes/core and actual
CRD schemas, then build and scan the exact deployment runner. Only after zero
HIGH/CRITICAL findings and complete schema coverage should M11 request approval
for a disposable-cluster runtime test. M12 cloud authorization is unchanged.

## Owner commands for blocked gates

After independently acquiring and verifying official artifacts into
`/OWNER/VERIFIED/deploy-inputs`:

```bash
docker build --network=none --pull=false --platform=linux/amd64 \
  --build-context artifacts=/OWNER/VERIFIED/deploy-inputs \
  -f deploy/gke/runners/Dockerfile.deploy \
  -t cogniflow-deploy-runner:m10-1 .
docker image inspect cogniflow-deploy-runner:m10-1 \
  --format '{{.Id}} {{.Architecture}} {{.Os}}'
trivy image --skip-db-update --skip-check-update \
  --severity HIGH,CRITICAL --exit-code 1 cogniflow-deploy-runner:m10-1
```

For schemas, first verify the validator and every schema/CRD bundle checksum,
then run kubeconform separately for core resources and each matching CRD schema
location; do not send CRDs to unrelated built-in schemas:

```bash
kubeconform -strict -summary -kubernetes-version 1.35.0 \
  -schema-location /OWNER/VERIFIED/kubernetes-json-schema \
  /OWNER/RENDERED/core-and-helm.yaml
kubeconform -strict -summary -kubernetes-version 1.35.0 \
  -schema-location /OWNER/VERIFIED/crd-schemas/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json \
  /OWNER/RENDERED/custom-resources.yaml
```
