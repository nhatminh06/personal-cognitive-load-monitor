# Local Kubernetes deployment

This deployment creates a one-node kind cluster and installs the existing Helm chart through Terraform. It is local-only: no GCP provider, cloud credentials, remote cluster, public ingress, KServe, or Spark runtime is involved.

```text
Terraform cluster state -> kind (one Docker node)
Terraform app state     -> namespace -> Helm release -> ClusterIP -> FastAPI pod
Host                    -> 127.0.0.1 port-forward --------------------^
```

## Prerequisites

Verify Docker, Terraform, kubectl, kind, and Helm are installed and that Docker is running:

```fish
docker version
terraform version
kubectl version --client
kind version
helm version
```

The verified environment used Docker 29.9.1, Terraform 1.15.9, kubectl 1.37.1, kind 0.33.0, and Helm 4.3.0. Provider versions and the kind node image are pinned in the Terraform lock files and variables.

## Create the cluster and deploy

Run these commands from the repository root. The two Terraform states deliberately separate cluster lifecycle from application lifecycle.

```fish
mkdir -p infra/terraform/local/.kube
terraform -chdir=infra/terraform/local/cluster init
terraform -chdir=infra/terraform/local/cluster plan -out=local.tfplan
terraform -chdir=infra/terraform/local/cluster apply local.tfplan

test (kubectl --kubeconfig infra/terraform/local/.kube/cogniflow-local.yaml \
  --context kind-cogniflow-local config current-context) = kind-cogniflow-local; or exit 1

docker build -t cognitive-load-api:local .
kind load docker-image cognitive-load-api:local --name cogniflow-local

terraform -chdir=infra/terraform/local/app init
terraform -chdir=infra/terraform/local/app plan -out=local.tfplan
terraform -chdir=infra/terraform/local/app apply local.tfplan
```

The exact kubeconfig and context are supplied on every kubectl command to prevent accidental operations against another cluster. Local state, plans, kubeconfig, and provider caches are ignored by Git; the provider lock files are committed.

## Verify and access

```fish
kubectl --kubeconfig infra/terraform/local/.kube/cogniflow-local.yaml \
  --context kind-cogniflow-local -n cognitive-load get pods,service

kubectl --kubeconfig infra/terraform/local/.kube/cogniflow-local.yaml \
  --context kind-cogniflow-local -n cognitive-load \
  logs deployment/cognitive-load-monitor

kubectl --kubeconfig infra/terraform/local/.kube/cogniflow-local.yaml \
  --context kind-cogniflow-local -n cognitive-load \
  port-forward service/cognitive-load-monitor 8000:80 --address 127.0.0.1
```

The UI is available at http://127.0.0.1:8000 and API documentation at http://127.0.0.1:8000/docs. In another terminal:

```fish
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/ready
curl --fail -X POST http://127.0.0.1:8000/predict \
  -H 'Content-Type: application/json' \
  -d '{"focus_minutes":120,"distraction_minutes":30,"tasks_due":3,"hours_to_deadline":24}'
curl --fail http://127.0.0.1:8000/metrics
```

The port-forward binds only to loopback. Stop it with Ctrl-C. If port 8000 is already occupied, stop the process that owns it or temporarily map another local port, for example `18000:80`.

## Security and resource boundaries

The local values use one API replica, `demo_rule` inference, a ClusterIP service, and bounded CPU and memory. The pod runs as UID 10001 with privilege escalation disabled, all Linux capabilities dropped, and a read-only root filesystem. Ingress, HPA, KServe, ServiceMonitor, and tracing are disabled. The application chart creates no host path, Docker socket, NodePort, load balancer, cloud credential, or Spark component.

kind's default kindnet does not enforce Kubernetes NetworkPolicy, so this configuration does not claim pod-level network isolation. Host access is limited by the loopback-only port-forward. Use a NetworkPolicy-capable CNI before relying on network policy as a security boundary.

## Rebuild or upgrade

After application changes, rebuild and load the same local tag, restart the deployment, and wait for rollout completion:

```fish
docker build -t cognitive-load-api:local .
kind load docker-image cognitive-load-api:local --name cogniflow-local
kubectl --kubeconfig infra/terraform/local/.kube/cogniflow-local.yaml \
  --context kind-cogniflow-local -n cognitive-load \
  rollout restart deployment/cognitive-load-monitor
kubectl --kubeconfig infra/terraform/local/.kube/cogniflow-local.yaml \
  --context kind-cogniflow-local -n cognitive-load \
  rollout status deployment/cognitive-load-monitor
```

Apply chart or local-values changes with `terraform -chdir=infra/terraform/local/app apply`. A subsequent plan should report no changes.

## Safe teardown

Destroy the application before the cluster. These commands target only the two local Terraform states and never touch `infra/terraform/gke` or named Module II Docker volumes.

```fish
terraform -chdir=infra/terraform/local/app destroy
terraform -chdir=infra/terraform/local/cluster destroy
```

Review each destroy plan before confirming. Do not use workspace-wide Docker volume cleanup commands.

## Verification record

On October 25, 2026, the pinned Kubernetes 1.36.1 kind node reached `Ready`, and Terraform created one cluster resource plus the `cognitive-load` namespace and Helm release. Both Terraform stages subsequently reported `No changes`. The pod reached `1/1 Running` with no restarts. Live requests returned healthy and ready states, a `MEDIUM` demo-rule prediction with `is_fallback=false`, and a matching `cognitive_load_predictions_total` metric. The full Python suite passed 78 tests at 88.67% coverage; Ruff, the documented MyPy check, Terraform validation, Helm lint, and restricted-manifest checks passed.

The kind node used approximately 903 MiB RAM at the recorded sample. Live API checks used loopback port 18000 because an unrelated existing uvicorn process occupied port 8000; Kubernetes still forwarded to the chart's port 80 service and API port 8000. The temporary verification port-forward was stopped, while the cluster and application were left running.
