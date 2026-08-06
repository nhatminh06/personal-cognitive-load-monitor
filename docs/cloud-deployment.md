# Cloud Deployment Guide (GKE)

**Status: none of this has been executed against a real cluster in this
repository's history.** This is a complete, ready-to-run guide, not a record
of a completed deployment. `gcloud` is not installed and no GCP credentials
are available in the environment these docs were written in — see
`docs/requirement-matrix.md` items 12–18 for exactly which requirements this
blocks and why.

## Decisions this guide assumes

- **Registry**: GHCR (already what CI publishes to — zero extra setup).
  Terraform also provisions a GCP Artifact Registry repo that goes unused
  under this choice; see `docs/architecture.md` for why that's left as a
  documented inconsistency rather than silently deleted.
- **KServe**: skipped for a first deployment. `INFERENCE_MODE=auto` (or
  explicit `local_model`) already serves genuine model predictions without
  it, so skipping KServe removes the heaviest, most failure-prone part of a
  first GKE rollout (Knative/Istio/cert-manager/KServe CRDs). Install it
  later by following the standard KServe quickstart and setting
  `kserve.enabled=true` plus a real `kserve.storageUri`.
- **Ingress host**: nip.io wildcard DNS from the ingress controller's
  external IP — no owned domain required for a demo.

## Steps

### 0. Prerequisites

```bash
brew install --cask google-cloud-sdk   # if gcloud is not already installed
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Requires a GCP project with billing enabled and owner/editor IAM.

### 1. Provision GKE with Terraform

```bash
cd infra/terraform/gke
cp terraform.tfvars.example terraform.tfvars
# edit: project_id, github_repository=<owner>/<repo>
terraform init
terraform plan
terraform apply
terraform output
```

This creates: the GKE cluster + node pool, a GCS model bucket (only used if
KServe is enabled later), an Artifact Registry repo (unused under the GHCR
choice above), and GitHub Actions Workload Identity Federation
(pool/provider/service account) for future automated deploys.

**Cost note**: a regional GKE cluster + node pool + load balancer bill
continuously. See step 8 for teardown.

### 2. Get cluster credentials

```bash
gcloud container clusters get-credentials $(terraform output -raw cluster_name) \
  --region $(terraform output -raw cluster_location) --project YOUR_PROJECT_ID
kubectl get nodes
```

### 3. Install cluster add-ons

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace

kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

kubectl get svc -n ingress-nginx ingress-nginx-controller -w   # wait for EXTERNAL-IP
```

KServe and the Prometheus/Loki/Tempo stack are not installed by this guide —
see "Extending this deployment" below.

### 4. Make the image pullable

```bash
gh run list --branch main --limit 3   # find the commit SHA CI built successfully
```

GHCR images pushed via `GITHUB_TOKEN` are private by default, and this Helm
chart has no `imagePullSecrets` support. Simplest fix: GitHub repo → Packages
→ `cognitive-load-api` → Package settings → Change visibility → **Public**.

### 5. Generate a real Basic Auth credential

```bash
htpasswd -nb admin 'YOUR_STRONG_PASSWORD'
```

Do not deploy with the chart's demo `admin/admin123` default.

### 6. Deploy with Helm

```bash
helm upgrade --install cognitive-load-monitor ./helm/cognitive-load-monitor \
  --namespace cognitive-load --create-namespace \
  --set image.repository=ghcr.io/<owner>/<repo>/cognitive-load-api \
  --set image.tag=<commit-sha-from-step-4> \
  --set kserve.enabled=false \
  --set serviceMonitor.enabled=false \
  --set config.enableTracing="false" \
  --set ingress.hosts[0].host=cognitive-load.<EXTERNAL-IP>.nip.io \
  --set-string basicAuth.auth='admin:<hash-from-step-5>'

kubectl rollout status deployment/cognitive-load-monitor -n cognitive-load --timeout=180s
```

`serviceMonitor.enabled=false` is required unless the Prometheus Operator
CRDs are installed — otherwise `helm install` fails outright with "no
matches for kind ServiceMonitor". `config.enableTracing=false` avoids
background OTLP connection-refused log spam since Tempo isn't deployed in
this minimal path.

### 7. Verify

```bash
curl -u admin:YOUR_STRONG_PASSWORD -X POST \
  http://cognitive-load.<EXTERNAL-IP>.nip.io/predict \
  -H "Content-Type: application/json" \
  -d '{"focus_minutes":60,"distraction_minutes":60,"tasks_due":5,"hours_to_deadline":12}'

curl -u admin:YOUR_STRONG_PASSWORD http://cognitive-load.<EXTERNAL-IP>.nip.io/model-info
curl -u admin:YOUR_STRONG_PASSWORD http://cognitive-load.<EXTERNAL-IP>.nip.io/metrics | grep cognitive_load_predictions_total

kubectl get hpa -n cognitive-load
```

Confirm an unauthenticated request is rejected:

```bash
curl -i http://cognitive-load.<EXTERNAL-IP>.nip.io/health   # expect 401
```

**Security note**: Basic Auth without TLS sends the password in a
base64-encoded (not encrypted) header. This guide does not configure TLS;
treat this deployment as a development/demo configuration only. Add a real
TLS certificate (e.g. via cert-manager + Let's Encrypt) before exposing this
to the public internet with real credentials.

### 8. Teardown

```bash
helm uninstall cognitive-load-monitor -n cognitive-load
helm uninstall ingress-nginx -n ingress-nginx
cd infra/terraform/gke && terraform destroy
```

## Extending this deployment

- **KServe**: follow the [KServe quickstart](https://kserve.github.io/website/latest/get_started/) to install Knative Serving + a networking layer + cert-manager + KServe CRDs, then redeploy with `--set kserve.enabled=true --set kserve.storageUri=gs://<bucket>/models/cognitive-load-classifier` (upload the model artifact to that bucket first).
- **Observability stack on GKE**: deploy `kube-prometheus-stack` (Prometheus + Grafana + the Prometheus Operator CRDs this chart's `ServiceMonitor` needs), Loki + Promtail, and Tempo via their respective Helm charts, in a separate `monitoring` namespace, before setting `serviceMonitor.enabled=true` / `config.enableTracing=true` here.
- **Automated deploys**: wire the Terraform outputs (`gcp_workload_identity_provider`, `gcp_service_account`, `gcp_project_id`, `gke_cluster`, `gke_location`) plus `APP_HOST` into GitHub Actions secrets so the existing `workflow_dispatch` `deploy` job works without manual `helm` commands. That job's current `helm upgrade` call does not pass the `kserve.enabled=false` / `serviceMonitor.enabled=false` / `config.enableTracing=false` flags used above — add them if you want an automated deploy to succeed against a cluster without KServe/Prometheus Operator installed.
