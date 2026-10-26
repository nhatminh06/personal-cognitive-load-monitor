"""Static safety checks for the KServe Standard-mode deployment contract."""

import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


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


def test_helm_kserve_render_is_custom_digest_pinned_and_internal():
    rendered = subprocess.run(
        [
            "helm", "template", "kserve", str(ROOT / "helm/cognitive-load-monitor"),
            "--namespace", "cognitive-load-kserve", "-f",
            str(ROOT / "helm/cognitive-load-monitor/values.phase5-kserve-local.yaml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "kind: InferenceService" in rendered
    assert "sklearn:" not in rendered
    assert "autoscaling.knative.dev" not in rendered
    assert "cognitive-load-kserve@sha256:" in rendered
    assert "KSERVE_ALLOWED_ORIGIN" in rendered
    assert "type: NodePort" not in rendered
    assert "kind: Ingress" not in rendered
