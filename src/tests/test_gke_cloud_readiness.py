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
    assert "network_policy {" not in cluster
    assert 'can(regex("^[0-9.]+/32$", network.cidr_block))' in variables
    assert "roles/container.developer" not in terraform
    assert "roles/container.clusterViewer" in terraform
    assert 'attribute.environment/production"' in terraform
    assert 'attribute.environment/production-release"' in terraform
    assert 'attribute.environment/production-knative"' in terraform
    assert 'attribute.environment/module1-production"' in terraform
    assert "github_actions_release.email" in terraform


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


def test_cloud_mlflow_clients_preserve_candidate_and_release_boundaries() -> None:
    registration = (ROOT / "src/cogniflow_data/kfp_tasks.py").read_text()
    packaging = (ROOT / "scripts/package_approved_model.py").read_text()
    release = (ROOT / ".github/workflows/release.yaml").read_text()

    assert '"approval_status": "candidate"' in registration
    assert registration.count("mlflow.artifacts.download_artifacts") >= 2
    assert 'tags.get("approval_status") != "approved"' in packaging
    assert "registered MLflow artifact integrity verification failed" in packaging
    assert "MLFLOW_TRACKING_URI" in release
    assert "mlflow.register_model" not in release


def test_regional_node_pool_is_exactly_two_demo_nodes() -> None:
    variables = (ROOT / "infra/terraform/gke/variables.tf").read_text()
    terraform = (ROOT / "infra/terraform/gke/main.tf").read_text()
    budget = yaml.safe_load((ROOT / "deploy/gke/resource-budget.yaml").read_text())

    assert 'default     = ["us-central1-a", "us-central1-b"]' in variables
    assert 'variable "nodes_per_zone"' in variables
    assert "default     = 1" in variables
    assert "node_count = var.nodes_per_zone" in terraform
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
    ingress = next(document for document in documents if document["kind"] == "Ingress")
    assert ingress["metadata"]["annotations"]["nginx.ingress.kubernetes.io/auth-secret"] == (
        "cogniflow-ingress-basic-auth"
    )
    assert ingress["spec"]["tls"][0]["secretName"] == "cogniflow-api-tls"
    assert ingress["metadata"]["annotations"]["nginx.ingress.kubernetes.io/auth-type"] == "basic"
    service = next(document for document in documents if document["kind"] == "Service")
    assert service["spec"]["type"] == "ClusterIP"
    policy = next(document for document in documents if document["kind"] == "NetworkPolicy")
    policy_text = yaml.safe_dump(policy)
    assert "169.254.169.254/32" in policy_text
    assert "0.0.0.0/0" not in result.stdout


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
    no_tls = _render("--set", "ingress.tls=null")

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


def test_deploy_uses_predictable_runner_and_verifies_exact_release() -> None:
    workflow = (ROOT / ".github/workflows/ci-cd.yaml").read_text()
    verifier = (ROOT / "scripts/verify_cloud_release.sh").read_text()

    assert "runs-on: [self-hosted, linux, x64, cogniflow-gke-deploy]" in workflow
    assert '--set-string "kserve.name=${MODEL_NAME}"' in workflow
    assert "scripts/verify_cloud_release.sh" in workflow
    assert "cosign v3.1.4 is required" in verifier
    assert "Trivy 0.76.1 is required" in verifier


def test_ci_test_build_and_manual_deploy_boundaries_are_explicit() -> None:
    workflow = (ROOT / ".github/workflows/ci-cd.yaml").read_text()

    assert "pull_request:" in workflow
    assert "uv run ruff check src scripts" in workflow
    assert "--cov-fail-under=81" in workflow
    assert "build:\n    name: Build and push Docker image\n    needs: test" in workflow
    assert "github.ref == 'refs/heads/main' && github.event_name == 'push'" in workflow
    assert "REQUIRE_MLFLOW" in workflow
    assert "cogniflow-module1-engineering-candidates" in workflow
    assert "mlflow.register_model" not in workflow
    assert "download_model_from_mlflow.py" not in workflow
    assert "deploy:\n    name: Manual deploy to Kubernetes with Helm\n    needs: test" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "name: production" in workflow
    assert "id-token: write" in workflow


def test_release_is_manual_approval_gated_and_never_deploys() -> None:
    workflow = (ROOT / ".github/workflows/release.yaml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "test:\n    name: Test exact release commit" in workflow
    assert "--cov-fail-under=81" in workflow
    assert "release:\n    needs: test" in workflow
    assert "name: production-release" in workflow
    assert "id-token: write" in workflow
    assert "model_run_id:" in workflow
    approval = workflow.index("- name: Approve exact educational candidate after Environment review")
    packaging = workflow.index("- name: Package independently approved model")
    assert approval < packaging
    assert "scripts/approve_model_candidate.py" in workflow
    assert "--expected-run-id \"$MODEL_RUN_ID\"" in workflow
    assert "--environment production-release" in workflow
    assert "--actor" not in workflow
    assert 'GITHUB_WORKFLOW_REF' in workflow
    assert "scripts/package_approved_model.py" in workflow
    assert "--provenance=mode=max --sbom=true" in workflow
    assert 'cosign sign "$reference"' in workflow
    assert 'trivy image --severity HIGH,CRITICAL' in workflow
    assert "kubectl" not in workflow
    assert "helm upgrade" not in workflow
    assert "GCP_RELEASE_WORKLOAD_IDENTITY_PROVIDER" in workflow
    assert "GCP_RELEASE_SERVICE_ACCOUNT" in workflow
    assert '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$' in workflow
    assert "module1-build.json" in workflow
    for identity in (
        "git_commit", "release_run_id", "model_name", "model_version", "model_run_id",
        "registered_artifact_sha256", "model_sha256", "dataset_sha256",
        "model_git_revision", "feature_schema_version", "label_provenance", "approval_scope",
        "api_image", "kserve_image",
    ):
        assert identity in workflow


def test_knative_deploy_is_separately_gated_and_verifies_all_release_images() -> None:
    workflow = (ROOT / ".github/workflows/deploy-knative.yaml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "name: production-knative" in workflow
    assert "id-token: write" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "scripts/render_production_knative.py" in workflow
    assert "scripts/verify_cloud_release.sh" in workflow
    for image in ("API_IMAGE", "KSERVE_IMAGE", "EVENT_CONSUMER_IMAGE", "ANOMALY_DETECTOR_IMAGE"):
        assert f'"${image}"' in workflow
    assert "docker build" not in workflow
    assert "cosign sign" not in workflow


def test_module1_deploy_is_manual_protected_oidc_and_knative_only() -> None:
    workflow = (ROOT / ".github/workflows/deploy-module1.yaml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "educational_demo:" in workflow
    assert "not production qualification" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "name: module1-production" in workflow
    assert "id-token: write" in workflow
    assert "actions: read" in workflow
    assert "google-github-actions/auth@" in workflow
    assert "GCP_WORKLOAD_IDENTITY_PROVIDER" in workflow
    assert "values.module1-knative.yaml" in workflow
    assert "scripts/verify_cloud_release.sh" in workflow
    assert "--atomic --timeout 10m" in workflow
    assert "replace_existing_release:" in workflow
    assert "scripts/module1_helm_guard.py" in workflow
    assert "scripts/module1_compatibility.py" in workflow
    assert "--require-qualified" in workflow
    assert workflow.count("if: ${{ ! inputs.educational_demo }}") == 2
    assert 'EDUCATIONAL_DEMO: ${{ inputs.educational_demo }}' in workflow
    assert "EXPECTED_GKE_CONTEXT" in workflow
    assert "helm get manifest cognitive-load-monitor" in workflow
    assert "enable-scale-to-zero" in workflow
    assert "inferenceservices.serving.kserve.io services.serving.knative.dev" in workflow
    assert '"0.21.0"' in workflow
    assert '"1.23.0"' in workflow
    assert '"1.31.3"' in workflow
    assert '"1.21.2"' in workflow
    assert '^1\\.34\\.[0-9]+' in workflow
    assert 'if [[ "$EDUCATIONAL_DEMO" != "true" ]]' in workflow
    assert 'if [[ "${{ inputs.educational_demo }}" == "true" ]]' in workflow
    assert '--set-string "config.appEnv=educational_demo"' in workflow
    assert '--set-string "config.kserveTimeoutSeconds=120"' in workflow
    assert "proxy-read-timeout=180" in workflow
    assert "revision-response-start-timeout-seconds" in workflow
    assert "revision-idle-timeout-seconds" in workflow
    assert "kpa.autoscaling.knative.dev" in workflow
    assert "kubectl get revision" in workflow
    assert "docker build" not in workflow
    assert "package_approved_model.py" not in workflow
    assert "approve_model_candidate.py" not in workflow
    assert "release_run_id:" in workflow
    assert '.path == ".github/workflows/release.yaml"' in workflow
    assert '.conclusion == "success"' in workflow
    assert "run-id: ${{ inputs.release_run_id }}" in workflow
    assert "ref: ${{ steps.manifest.outputs.git_commit }}" in workflow
    assert "steps.manifest.outputs.api_image" in workflow
    assert "steps.manifest.outputs.kserve_image" in workflow
    for unrelated_input in (
        "inputs.api_image", "inputs.kserve_image", "inputs.model_name",
        "inputs.model_version", "inputs.model_sha256",
        "inputs.artifact_sha256", "inputs.dataset_sha256",
    ):
        assert unrelated_input not in workflow


def test_module1_deploy_bootstraps_only_owned_native_cloud_secrets() -> None:
    workflow = (ROOT / ".github/workflows/deploy-module1.yaml").read_text()

    bootstrap = workflow.index("- name: Prepare owned native application Secrets")
    deployment = workflow.index("- name: Deploy explicit Module I Knative mode")
    assert bootstrap < deployment
    for protected_input in (
        "secrets.COGNIFLOW_API_KEY",
        "secrets.COGNIFLOW_INGRESS_AUTH",
        "secrets.COGNIFLOW_TLS_CERT",
        "secrets.COGNIFLOW_TLS_KEY",
    ):
        assert protected_input in workflow
    assert '--from-file=COGNIFLOW_API_KEY="$secret_dir/api-key"' in workflow
    assert '--from-file=auth="$secret_dir/ingress-auth"' in workflow
    assert "kubectl create secret tls cogniflow-api-tls" in workflow
    assert 'trap \'rm -rf -- "$secret_dir"\' EXIT' in workflow
    assert "Required protected credential is missing" in workflow
    assert "Refusing to replace foreign-owned Secret" in workflow
    assert "cogniflow.io/deployment-owner=module1-knative" in workflow
    assert "--from-literal" not in workflow
    assert "deploy/gke/external-secret.yaml" not in workflow
    assert "ExternalSecret" not in workflow


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
