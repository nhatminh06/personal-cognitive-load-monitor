from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).parents[2]
LOCAL_TERRAFORM = ROOT / "infra/terraform/local"


def test_local_terraform_is_explicit_and_cloud_free() -> None:
    text = "\n".join(path.read_text() for path in LOCAL_TERRAFORM.rglob("*.tf"))

    assert 'source  = "tehcyx/kind"' in text
    assert 'default     = "cogniflow-local"' in text
    assert 'default     = "kind-cogniflow-local"' in text
    assert "config_context = var.kubernetes_context" in text
    assert 'abspath("${path.module}/../../../../helm/cognitive-load-monitor")' in text
    for forbidden in ("google", "aws", "azurerm", "gke", "load_balancer"):
        assert forbidden not in text.lower()


def test_local_helm_values_are_private_and_resource_bounded() -> None:
    values = yaml.safe_load((ROOT / "helm/cognitive-load-monitor/values.local.yaml").read_text())

    assert values["replicaCount"] == 1
    assert values["image"]["pullPolicy"] == "Never"
    assert values["config"]["appEnv"] == "development"
    assert values["config"]["inferenceMode"] == "demo_rule"
    assert values["service"]["type"] == "ClusterIP"
    assert values["autoscaling"]["enabled"] is False
    assert values["kserve"]["enabled"] is False
    assert values["ingress"]["enabled"] is False
    assert values["serviceMonitor"]["enabled"] is False
    assert values["networkPolicy"]["enabled"] is False
    assert values["resources"]["limits"] == {"cpu": "250m", "memory": "256Mi"}


def test_phase3_helm_release_is_isolated_and_digest_pinned() -> None:
    chart = ROOT / "helm/cognitive-load-monitor"
    values = chart / "values.phase3-local.yaml"
    digest = "sha256:" + "a" * 64
    rendered = subprocess.run(
        [
            "helm", "template", "cognitive-load-phase3", str(chart),
            "--namespace", "cognitive-load-phase3",
            "--values", str(values),
            "--set-string", f"image.digest={digest}",
            "--set-string", "config.modelVersion=7",
            "--set-string", "config.modelSha256=" + "b" * 64,
            "--set-string", "config.modelArtifactSha256=" + "c" * 64,
            "--set-string", "config.modelDatasetSha256=" + "d" * 64,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert f'image: "cognitive-load-api-phase3@{digest}"' in rendered
    assert "imagePullPolicy: Never" in rendered
    assert "type: ClusterIP" in rendered
    assert 'INFERENCE_MODE: "local_model"' in rendered
    assert "kind: Ingress" not in rendered
    assert "kind: InferenceService" not in rendered
    assert "readOnlyRootFilesystem: true" in rendered
    assert "runAsNonRoot: true" in rendered


def test_phase3_helm_refuses_mutable_image_reference() -> None:
    result = subprocess.run(
        [
            "helm", "template", "cognitive-load-phase3",
            str(ROOT / "helm/cognitive-load-monitor"),
            "--values", str(ROOT / "helm/cognitive-load-monitor/values.phase3-local.yaml"),
            "--set-string", "config.modelVersion=7",
            "--set-string", "config.modelSha256=" + "b" * 64,
            "--set-string", "config.modelArtifactSha256=" + "c" * 64,
            "--set-string", "config.modelDatasetSha256=" + "d" * 64,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "image.digest must be a non-placeholder sha256 digest" in result.stderr
