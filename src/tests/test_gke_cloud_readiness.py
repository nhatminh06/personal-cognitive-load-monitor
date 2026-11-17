from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from scripts.render_production_knative import render


ROOT = Path(__file__).parents[2]
CHART = ROOT / "helm/cognitive-load-monitor"
GKE_VALUES = CHART / "values.gke.yaml"
VALID_OVERRIDES = [
    "--set-string", "image.digest=sha256:" + "a" * 64,
    "--set-string", "kserve.image.digest=sha256:" + "b" * 64,
    "--set-string", "config.modelName=cognitive-load-classifier",
    "--set-string", "config.modelVersion=1",
    "--set-string", "config.modelSha256=" + "c" * 64,
    "--set-string", "config.modelArtifactSha256=" + "d" * 64,
    "--set-string", "config.modelDatasetSha256=" + "e" * 64,
]


def _render(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "helm", "template", "cogniflow", str(CHART),
            "--namespace", "cogniflow", "-f", str(GKE_VALUES),
            *VALID_OVERRIDES, *extra,
        ],
        capture_output=True,
        text=True,
    )


def test_gke_terraform_has_private_bounded_identity_and_storage_controls() -> None:
    terraform = "\n".join(
        path.read_text() for path in (ROOT / "infra/terraform/gke").glob("*.tf")
    )

    for expected in (
        'enable_private_nodes    = true',
        'datapath_provider   = "ADVANCED_DATAPATH"',
        'deletion_protection = true',
        'public_access_prevention    = "enforced"',
        'uniform_bucket_level_access = true',
        'force_destroy               = false',
        'role   = "roles/storage.objectViewer"',
        'role   = "roles/storage.objectAdmin"',
        'role               = "roles/iam.workloadIdentityUser"',
        'role      = "roles/secretmanager.secretAccessor"',
    ):
        assert expected in terraform
    assert "google_service_account_key" not in terraform
    assert "spark" not in terraform.lower()
    cluster = (ROOT / "infra/terraform/gke/main.tf").read_text()
    variables = (ROOT / "infra/terraform/gke/variables.tf").read_text()
    assert 'min_master_version  = "1.35"' in cluster
    assert "channel in var.budget_notification_channel_ids" in variables
    assert "monitoring_notification_channels = var.budget_notification_channel_ids" in cluster
    assert "disable_default_iam_recipients   = true" in cluster
    assert "network_policy {" not in cluster
    assert 'can(regex("^[0-9.]+/32$", network.cidr_block))' in variables
    assert "roles/container.developer" not in terraform
    assert "roles/container.clusterViewer" in terraform
    assert 'attribute.environment/production"' in terraform
    assert 'attribute.environment/production-release"' in terraform
    assert 'attribute.environment/production-knative"' in terraform
    assert 'attribute.environment/module1-production"' in terraform
    assert "github_actions_release.email" in terraform

    backend = (ROOT / "infra/terraform/gke/backend.tf.example").read_text()
    assert 'prefix = "cogniflow/gke"' in backend
    assert "force_destroy=false" in backend
    assert "90-day" in backend
    assert "Do not set a bucket retention" in backend

    runbook = (ROOT / "docs/cloud-deployment.md").read_text()
    assert "2 HIGH findings in kubectl 1.35.10" in runbook
    assert "13-HIGH image remains historical evidence only" in runbook
    assert "13 HIGH\nfindings" in (ROOT / "deploy/gke/runners/README.md").read_text()
    assert "The separate\n`$75` contingency" in runbook
    assert "cogniflow-retain-rwo" in runbook
    assert "cogniflow-delete-rwo" in runbook
    storage_gate = runbook.index("kubectl apply -f deploy/gke/storageclasses.yaml")
    assert storage_gate < runbook.index("render and apply MLflow")
    assert storage_gate < runbook.index("protected Eventing workflow create")
    assert "namespace-scoped deployment identities must not" in runbook


def test_cloud_mlflow_uses_private_sqlite_registry_and_gcs_artifacts() -> None:
    documents = list(yaml.safe_load_all((ROOT / "deploy/gke/mlflow.yaml").read_text()))
    by_kind = {document["kind"]: document for document in documents}
    deployment = by_kind["Deployment"]
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    args = container["args"]

    assert set(by_kind) == {
        "Namespace", "ServiceAccount", "PersistentVolumeClaim", "Deployment",
        "Service", "NetworkPolicy",
    }
    assert by_kind["Service"]["spec"]["type"] == "ClusterIP"
    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["strategy"]["type"] == "Recreate"
    assert container["image"] == "SET_MLFLOW_IMAGE"
    assert "--backend-store-uri" in args
    assert "--registry-store-uri" in args
    assert args.count("sqlite:////mlflow/metadata/mlflow.db") == 2
    assert "gs://SET_MLFLOW_BUCKET/artifacts" in args
    assert "--serve-artifacts" in args
    assert args[args.index("--workers") + 1] == "1"
    allowed_hosts = args[args.index("--allowed-hosts") + 1]
    assert allowed_hosts == (
        "mlflow.mlflow.svc.cluster.local:5000,mlflow.mlflow.svc:5000,"
        "mlflow:5000,localhost:5000,127.0.0.1:5000"
    )
    assert "*" not in allowed_hosts
    assert all(
        container[probe]["httpGet"] == {"path": "/health", "port": "http"}
        for probe in ("startupProbe", "readinessProbe", "livenessProbe")
    )
    assert {mount["mountPath"] for mount in container["volumeMounts"]} >= {
        "/mlflow/metadata", "/tmp",
    }
    assert by_kind["PersistentVolumeClaim"]["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert by_kind["PersistentVolumeClaim"]["spec"]["storageClassName"] == (
        "cogniflow-retain-rwo"
    )
    assert by_kind["ServiceAccount"]["metadata"]["annotations"] == {
        "iam.gke.io/gcp-service-account": (
            "cogniflow-mlflow@SET_PROJECT.iam.gserviceaccount.com"
        )
    }
    policy = by_kind["NetworkPolicy"]
    ingress_namespaces = {
        source["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"]
        for source in policy["spec"]["ingress"][0]["from"]
    }
    assert ingress_namespaces == {"mlflow", "kubeflow", "cogniflow-release"}
    assert "Ingress" not in {document["kind"] for document in documents}

    terraform = (ROOT / "infra/terraform/gke/main.tf").read_text()
    assert 'role   = "roles/storage.objectAdmin"' in terraform
    assert "serviceAccount:${var.project_id}.svc.id.goog[mlflow/mlflow]" in terraform
    assert "force_destroy               = false" in terraform
    assert "public_access_prevention    = \"enforced\"" in terraform
    assert "uv sync --frozen --extra kubeflow" in (ROOT / "Dockerfile.kfp").read_text()
    assert 'name = "google-cloud-storage"' in (ROOT / "uv.lock").read_text()


def test_gke_storage_classes_make_placement_and_reclaim_policy_explicit() -> None:
    classes = {
        document["metadata"]["name"]: document
        for document in yaml.safe_load_all(
            (ROOT / "deploy/gke/storageclasses.yaml").read_text()
        )
    }
    assert set(classes) == {"cogniflow-retain-rwo", "cogniflow-delete-rwo"}
    assert {item["provisioner"] for item in classes.values()} == {
        "pd.csi.storage.gke.io"
    }
    assert {item["volumeBindingMode"] for item in classes.values()} == {
        "WaitForFirstConsumer"
    }
    assert classes["cogniflow-retain-rwo"]["reclaimPolicy"] == "Retain"
    assert classes["cogniflow-delete-rwo"]["reclaimPolicy"] == "Delete"

    for name in ("consumer.yaml", "dead-letter.yaml", "anomaly.yaml"):
        claims = [
            document
            for document in yaml.safe_load_all((ROOT / "deploy/knative" / name).read_text())
            if document and document["kind"] == "PersistentVolumeClaim"
        ]
        assert claims
        assert all(
            claim["spec"]["storageClassName"] == "cogniflow-delete-rwo"
            for claim in claims
        )


def test_cloud_mlflow_clients_preserve_candidate_and_release_boundaries() -> None:
    registration = (ROOT / "src/cogniflow_data/kfp_tasks.py").read_text()
    packaging = (ROOT / "scripts/package_approved_model.py").read_text()

    assert '"approval_status": "candidate"' in registration
    assert registration.count("mlflow.artifacts.download_artifacts") >= 2
    assert 'tags.get("approval_status") != "approved"' in packaging
    assert "registered MLflow artifact integrity verification failed" in packaging
    assert not (ROOT / ".github/workflows/release.yaml").exists()


def test_regional_node_pool_is_exactly_two_demo_nodes() -> None:
    variables = (ROOT / "infra/terraform/gke/variables.tf").read_text()
    terraform = (ROOT / "infra/terraform/gke/main.tf").read_text()
    budget = yaml.safe_load((ROOT / "deploy/gke/resource-budget.yaml").read_text())

    assert 'default     = ["us-central1-a", "us-central1-b"]' in variables
    assert 'variable "nodes_per_zone"' in variables
    assert "default     = 1" in variables
    assert "node_count = var.nodes_per_zone" in terraform
    assert "max_surge       = 0" in terraform
    assert "max_unavailable = 1" in terraform
    assert budget["node_pool"] == {
        "nodes": 2,
        "machine_type": "e2-standard-4",
        "capacity": {"cpu_millicores": 8000, "memory_mib": 32768},
        "system_reserve_percent": 20,
    }
    assert budget["required_requests"]["mlflow_sqlite"] == {
        "cpu_millicores": 100,
        "memory_mib": 512,
    }
    assert budget["sequential_runner_requests"] == {
        "private_packaging_runner": {"cpu_millicores": 500, "memory_mib": 1024},
        "deployment_runner": {"cpu_millicores": 250, "memory_mib": 512},
    }


def test_gke_helm_renders_exact_images_tls_separate_identities_and_narrow_network() -> None:
    result = _render()
    assert result.returncode == 0, result.stderr
    documents = [document for document in yaml.safe_load_all(result.stdout) if document]
    images = [
        container["image"]
        for document in documents
        for container in document.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    ]
    inference = next(document for document in documents if document["kind"] == "InferenceService")
    images.append(inference["spec"]["predictor"]["containers"][0]["image"])

    assert all("@sha256:" in image for image in images)
    assert inference["metadata"]["annotations"]["serving.kserve.io/deploymentMode"] == "Standard"
    assert inference["spec"]["predictor"]["serviceAccountName"] == "cogniflow-kserve"
    assert inference["spec"]["predictor"]["volumes"][0]["emptyDir"]["sizeLimit"] == "64Mi"
    deployment = next(document for document in documents if document["kind"] == "Deployment")
    assert deployment["spec"]["template"]["spec"]["securityContext"]["seccompProfile"] == {
        "type": "RuntimeDefault",
    }
    assert {"secretRef": {"name": "cogniflow-api"}} in (
        deployment["spec"]["template"]["spec"]["containers"][0]["envFrom"]
    )
    assert "Ingress" not in {document["kind"] for document in documents}
    service = next(document for document in documents if document["kind"] == "Service")
    assert service["spec"]["type"] == "ClusterIP"
    policy = next(document for document in documents if document["kind"] == "NetworkPolicy")
    policy_text = yaml.safe_dump(policy)
    ingress_namespaces = {
        source["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"]
        for rule in policy["spec"]["ingress"]
        for source in rule.get("from", [])
        if "namespaceSelector" in source
    }
    assert "gke-managed-system" not in ingress_namespaces
    assert ingress_namespaces == {"monitoring"}
    assert "169.254.169.254/32" in policy_text
    assert "0.0.0.0/0" not in result.stdout
    assert {"Ingress", "Gateway", "HTTPRoute"}.isdisjoint(
        document["kind"] for document in documents
    )


def test_hpa_targets_api_with_bounded_explicit_behavior() -> None:
    result = _render()
    assert result.returncode == 0, result.stderr
    documents = [document for document in yaml.safe_load_all(result.stdout) if document]
    hpa = next(document for document in documents if document["kind"] == "HorizontalPodAutoscaler")
    deployment = next(document for document in documents if document["kind"] == "Deployment")

    assert hpa["spec"]["scaleTargetRef"] == {
        "apiVersion": "apps/v1", "kind": "Deployment", "name": deployment["metadata"]["name"],
    }
    assert hpa["spec"]["minReplicas"] == 2
    assert hpa["spec"]["maxReplicas"] == 5
    assert hpa["spec"]["behavior"]["scaleUp"]["policies"][0]["value"] == 100
    assert hpa["spec"]["behavior"]["scaleDown"]["stabilizationWindowSeconds"] == 300
    assert deployment["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] == "100m"


def test_hpa_rejects_invalid_production_bounds() -> None:
    for override in (
        ("--set", "autoscaling.minReplicas=0"),
        ("--set", "autoscaling.minReplicas=6"),
        ("--set", "autoscaling.targetCPUUtilizationPercentage=101"),
    ):
        result = _render(*override)
        assert result.returncode != 0
        assert "autoscaling" in result.stderr


def test_gke_helm_fails_closed_on_placeholder_digest_and_missing_tls() -> None:
    placeholder = subprocess.run(
        ["helm", "template", "cogniflow", str(CHART), "-f", str(GKE_VALUES)],
        capture_output=True,
        text=True,
    )
    no_tls = _render("--set", "ingress.enabled=true", "--set", "ingress.tls=null")

    assert placeholder.returncode != 0
    assert "non-placeholder" in placeholder.stderr
    assert no_tls.returncode != 0
    assert "ingress.tls is required for production ingress" in no_tls.stderr


def test_gke_helm_rejects_model_identity_and_broker_mismatches() -> None:
    model_mismatch = _render("--set-string", "kserve.name=different-model")
    broker_mismatch = _render(
        "--set-string",
        "config.inferenceActivityDestination=http://broker-ingress.knative-eventing.svc.cluster.local/cogniflow-eventing/missing",
    )

    assert model_mismatch.returncode != 0
    assert "matching kserve.name" in model_mismatch.stderr
    assert broker_mismatch.returncode != 0
    assert "must match the configured Knative Broker" in broker_mismatch.stderr


def test_gke_helm_rejects_kserve_incompatible_model_names() -> None:
    for name in ("Uppercase", "has.dot", "has_underscore", "-leading", "trailing-", "a" * 64):
        result = _render(
            "--set-string", f"kserve.name={name}",
            "--set-string", f"config.modelName={name}",
        )
        assert result.returncode != 0
        assert "lowercase DNS label" in result.stderr


def test_production_broker_destination_matches_versioned_manifests() -> None:
    values = yaml.safe_load(GKE_VALUES.read_text())
    broker = yaml.safe_load((ROOT / "deploy/knative/broker.yaml").read_text())
    triggers = [
        yaml.safe_load((ROOT / "deploy/knative/trigger.yaml").read_text()),
        yaml.safe_load((ROOT / "deploy/knative/anomaly-trigger.yaml").read_text()),
    ]
    expected = (
        "http://broker-ingress.knative-eventing.svc.cluster.local/"
        f"{broker['metadata']['namespace']}/{broker['metadata']['name']}"
    )

    assert values["config"]["inferenceActivityDestination"] == expected
    assert values["eventing"] == {
        "brokerNamespace": broker["metadata"]["namespace"],
        "brokerName": broker["metadata"]["name"],
    }
    assert all(trigger["spec"]["broker"] == broker["metadata"]["name"] for trigger in triggers)
    assert all(trigger["metadata"]["namespace"] == broker["metadata"]["namespace"] for trigger in triggers)


def test_cloud_guardrails_and_two_node_budget_are_enforceable() -> None:
    guardrails = list(
        yaml.safe_load_all((ROOT / "deploy/gke/cogniflow-guardrails.yaml").read_text())
    )
    namespace = next(item for item in guardrails if item["kind"] == "Namespace")
    labels = namespace["metadata"]["labels"]
    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert {item["kind"] for item in guardrails} >= {
        "ResourceQuota", "LimitRange", "NetworkPolicy", "RoleBinding",
    }

    budget = yaml.safe_load((ROOT / "deploy/gke/resource-budget.yaml").read_text())
    usable_cpu = (
        budget["node_pool"]["capacity"]["cpu_millicores"]
        * (100 - budget["node_pool"]["system_reserve_percent"])
        // 100
    )
    usable_memory = (
        budget["node_pool"]["capacity"]["memory_mib"]
        * (100 - budget["node_pool"]["system_reserve_percent"])
        // 100
    )
    assert sum(item["cpu_millicores"] for item in budget["required_requests"].values()) <= usable_cpu
    assert sum(item["memory_mib"] for item in budget["required_requests"].values()) <= usable_memory


def test_publication_candidate_ci_has_no_release_or_cloud_execution() -> None:
    workflows = ROOT / ".github/workflows"
    assert {path.name for path in workflows.glob("*.yaml")} == {
        "ci-cd.yaml", "release-qualification.yaml",
    }
    ci = (workflows / "ci-cd.yaml").read_text()
    assert "pull_request:" in ci
    assert "uv run ruff check src scripts" in ci
    assert "--cov-fail-under=81" in ci
    assert "fetch-depth: 0" in ci
    assert "gitleaks git" in ci and "gitleaks dir" in ci
    for forbidden in (
        "workflow_dispatch", "id-token: write", "packages: write", "docker push",
        "helm upgrade", "kubectl", "google-github-actions", "docker/login-action",
    ):
        assert forbidden not in ci


def test_production_knative_render_replaces_all_development_images() -> None:
    registry = "us-central1-docker.pkg.dev/example-project/cogniflow-images"
    rendered = render(
        ROOT / "deploy/knative",
        {
            "event_consumer": f"{registry}/event-consumer@sha256:" + "a" * 64,
            "anomaly_detector": f"{registry}/anomaly-detector@sha256:" + "b" * 64,
        },
    )

    assert ":dev" not in rendered
    assert "imagePullPolicy: Never" not in rendered
    assert rendered.count("@sha256:") == 4


def test_production_knative_render_rejects_mutable_images() -> None:
    try:
        render(
            ROOT / "deploy/knative",
            {
                "event_consumer": "us-central1-docker.pkg.dev/example-project/cogniflow-images/event-consumer:latest",
                "anomaly_detector": "us-central1-docker.pkg.dev/example-project/cogniflow-images/anomaly-detector@sha256:" + "b" * 64,
            },
        )
    except ValueError as error:
        assert "Artifact Registry digest" in str(error)
    else:
        raise AssertionError("mutable production image was accepted")
