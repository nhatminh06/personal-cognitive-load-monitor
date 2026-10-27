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
    assert "ipBlock" not in yaml.safe_dump(policy)
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
