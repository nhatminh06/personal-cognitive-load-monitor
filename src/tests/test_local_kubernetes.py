from __future__ import annotations

from pathlib import Path

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
