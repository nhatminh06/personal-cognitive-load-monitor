from __future__ import annotations

from pathlib import Path
import subprocess

import yaml


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
    assert inference["spec"]["predictor"]["serviceAccountName"] == "cogniflow-kserve"
    ingress = next(document for document in documents if document["kind"] == "Ingress")
    assert ingress["spec"]["tls"][0]["secretName"] == "cogniflow-api-tls"
    policy = next(document for document in documents if document["kind"] == "NetworkPolicy")
    policy_text = yaml.safe_dump(policy)
    assert "169.254.169.254/32" in policy_text
    assert "0.0.0.0/0" not in result.stdout


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
