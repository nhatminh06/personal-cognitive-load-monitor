"""Static safety checks for the KServe Standard-mode deployment contract."""

import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[2]
CHART = ROOT / "helm/cognitive-load-monitor"
VALID_VALUES = [
    "--set", "image.digest=sha256:" + "1" * 64,
    "--set", "kserve.image.digest=sha256:" + "2" * 64,
    "--set", "config.modelSha256=" + "3" * 64,
    "--set", "config.modelArtifactSha256=" + "4" * 64,
    "--set", "config.modelDatasetSha256=" + "5" * 64,
]


def test_standalone_inferenceservice_is_internal_and_restricted():
    namespace = yaml.safe_load((ROOT / "kserve/namespace.yaml").read_text())
    service_account = yaml.safe_load((ROOT / "kserve/serviceaccount.yaml").read_text())
    service = yaml.safe_load((ROOT / "kserve/inferenceservice.yaml").read_text())
    container = service["spec"]["predictor"]["containers"][0]

    assert namespace["metadata"]["name"] == "cognitive-load-kserve"
    assert service_account["automountServiceAccountToken"] is False
    assert service["kind"] == "InferenceService"
    assert service["metadata"]["namespace"] == "cognitive-load-kserve"
    assert service["spec"]["predictor"]["serviceAccountName"] == "cognitive-load-kserve"
    assert "@sha256:" in container["image"]
    assert container["securityContext"]["runAsUser"] == 10001
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert container["resources"]["limits"] == {"cpu": "1", "memory": "1Gi"}


def test_kserve_image_keeps_production_defaults_and_supports_engineering_package():
    dockerfile = (ROOT / "Dockerfile.kserve").read_text()

    assert "ARG MODEL_PACKAGE_DIR=build/model-package" in dockerfile
    assert "COPY ${MODEL_PACKAGE_DIR}/cognitive_load_model.skops" in dockerfile
    assert "COPY ${MODEL_PACKAGE_DIR}/model-package.json" in dockerfile
    assert "COPY scripts/serve_engineering_model.py" in dockerfile
    assert "USER appuser" in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "cogniflow_kserve.server"]' in dockerfile


def test_helm_kserve_render_is_custom_digest_pinned_and_internal():
    rendered = subprocess.run(
        [
            "helm", "template", "kserve", str(ROOT / "helm/cognitive-load-monitor"),
            "--namespace", "cognitive-load-kserve", "-f",
            str(ROOT / "helm/cognitive-load-monitor/values.phase5-kserve-local.yaml"),
            *VALID_VALUES,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "kind: InferenceService" in rendered
    assert 'serving.kserve.io/deploymentMode: "Standard"' in rendered
    assert "sklearn:" not in rendered
    assert "autoscaling.knative.dev" not in rendered
    assert "cognitive-load-kserve@sha256:" in rendered
    assert "KSERVE_ALLOWED_ORIGIN" in rendered
    assert "type: NodePort" not in rendered
    assert "kind: Ingress" not in rendered


def test_module1_knative_mode_renders_explicit_scale_to_zero_contract():
    rendered = subprocess.run(
        [
            "helm", "template", "module1", str(CHART), "--namespace", "cogniflow",
            "-f", str(CHART / "values.gke.yaml"),
            "-f", str(CHART / "values.module1-knative.yaml"),
            "--set-string", "config.modelName=cognitive-load-classifier",
            "--set-string", "config.modelVersion=1",
            *VALID_VALUES,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert 'serving.kserve.io/deploymentMode: "Knative"' in rendered
    assert "autoscaling.knative.dev/class: kpa.autoscaling.knative.dev" in rendered
    assert 'autoscaling.knative.dev/min-scale: "0"' in rendered
    assert 'autoscaling.knative.dev/max-scale: "3"' in rendered
    assert 'autoscaling.knative.dev/target: "1"' in rendered
    assert 'KSERVE_TIMEOUT_SECONDS: "30"' in rendered
    assert 'nginx.ingress.kubernetes.io/proxy-read-timeout: "35"' in rendered


def test_standard_mode_keeps_short_kserve_timeout():
    rendered = subprocess.run(
        [
            "helm", "template", "standard", str(CHART), "--namespace", "cogniflow",
            "-f", str(CHART / "values.gke.yaml"),
            "--set-string", "config.modelName=cognitive-load-classifier",
            "--set-string", "config.modelVersion=1",
            *VALID_VALUES,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert 'serving.kserve.io/deploymentMode: "Standard"' in rendered
    assert 'KSERVE_TIMEOUT_SECONDS: "3"' in rendered


@pytest.mark.parametrize(
    "override",
    (
        "kserve.deploymentMode=Serverless",
        "kserve.knativeAutoscaling.minScale=1",
        "kserve.knativeAutoscaling.maxScale=0",
        "kserve.knativeAutoscaling.targetConcurrency=0",
    ),
)
def test_module1_knative_mode_rejects_invalid_autoscaling(override):
    result = subprocess.run(
        [
            "helm", "template", "module1", str(CHART), "--namespace", "cogniflow",
            "-f", str(CHART / "values.gke.yaml"),
            "-f", str(CHART / "values.module1-knative.yaml"),
            "--set-string", "config.modelName=cognitive-load-classifier",
            "--set-string", "config.modelVersion=1",
            *VALID_VALUES,
            "--set-string", override,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_helm_rejects_all_documentation_sentinels():
    result = subprocess.run(
        [
            "helm", "template", "kserve", str(ROOT / "helm/cognitive-load-monitor"),
            "--namespace", "cognitive-load-kserve", "-f",
            str(ROOT / "helm/cognitive-load-monitor/values.phase5-kserve-local.yaml"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "non-placeholder" in result.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        ["--set", "image.digest=sha256:" + "0" * 64],
        ["--set", "kserve.image.digest=sha256:" + "0" * 64],
        ["--set", "config.modelSha256=" + "0" * 64],
        ["--set", "config.modelArtifactSha256=" + "0" * 64],
        ["--set", "config.modelDatasetSha256=" + "0" * 64],
        ["--set", "config.modelVersion=REPLACE"],
        ["--set", "config.modelName=CHANGE_ME"],
        ["--set", "config.kserveTimeoutSeconds=0"],
        ["--set", "config.kserveTimeoutSeconds=31"],
        ["--set", "config.kserveTimeoutSeconds=NaN"],
    ],
)
def test_helm_rejects_each_placeholder_value(overrides):
    values = VALID_VALUES + overrides
    result = subprocess.run(
        [
            "helm", "template", "kserve", str(ROOT / "helm/cognitive-load-monitor"),
            "--namespace", "cognitive-load-kserve", "-f",
            str(ROOT / "helm/cognitive-load-monitor/values.phase5-kserve-local.yaml"),
            *values,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
