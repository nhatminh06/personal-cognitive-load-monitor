from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.module1_compatibility import validate_matrix, validate_runtime_snapshot


ROOT = Path(__file__).parents[2]
MATRIX = json.loads((ROOT / "docs/module1/compatibility-matrix.json").read_text())


def qualified() -> tuple[dict, dict]:
    matrix = deepcopy(MATRIX)
    candidate = matrix["candidates"][-1]
    candidate["support_status"] = "qualified"
    candidate["integration_evidence"] = "isolated exact-matrix acceptance evidence"
    candidate["suitable"] = True
    matrix["qualification_status"] = "QUALIFIED"
    matrix["selected_candidate"] = candidate["id"]
    return matrix, candidate


def snapshot(candidate: dict) -> dict:
    digest = "a" * 64
    controllers = {
        name: {"available": True, "image": f"registry.example/{name.replace('/', '-')}@sha256:{digest}"}
        for name in (
            "kserve/kserve-controller-manager", "knative-serving/controller",
            "knative-serving/autoscaler", "knative-serving/activator",
            "knative-serving/webhook", "cert-manager/cert-manager",
        )
    }
    origin = "http://cognitive-load-classifier-predictor.cogniflow.svc.cluster.local"
    return {
        "kserve": candidate["kserve"], "knative_serving": candidate["knative_serving"],
        "kubernetes": candidate["kubernetes"], "networking": candidate["networking"],
        "cert_manager": candidate["cert_manager"], "namespace": "cogniflow",
        "model_name": "cognitive-load-classifier",
        "crds": ["inferenceservices.serving.kserve.io", "configurations.serving.knative.dev", "revisions.serving.knative.dev"],
        "controllers": controllers,
        "autoscaler": {"enable-scale-to-zero": "true", "stable-window": "60s", "scale-to-zero-grace-period": "30s"},
        "revision_annotations": {
            "autoscaling.knative.dev/class": "kpa.autoscaling.knative.dev",
            "autoscaling.knative.dev/min-scale": "0", "autoscaling.knative.dev/max-scale": "3",
            "autoscaling.knative.dev/target": "1",
        },
        "routes": {"origin": origin, "predict": f"{origin}/v1/models/cognitive-load-classifier:predict",
                   "metadata": f"{origin}/v1/models/cognitive-load-classifier/metadata"},
        "timeouts": {"api_seconds": 30, "ingress_seconds": 35, "revision_seconds": 35,
                     "response_start_seconds": 35, "idle_seconds": 35},
    }


def test_published_matrix_is_valid_but_fail_closed() -> None:
    validate_matrix(MATRIX)
    with pytest.raises(ValueError, match="BLOCKED"):
        validate_matrix(MATRIX, require_qualified=True)


def test_exact_qualified_runtime_snapshot_is_accepted() -> None:
    matrix, candidate = qualified()
    validate_matrix(matrix, require_qualified=True)
    validate_runtime_snapshot(snapshot(candidate), candidate)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda value: value["controllers"].pop("knative-serving/activator"), "controller inventory"),
        (lambda value: value.__setitem__("knative_serving", "1.21.1"), "runtime versions"),
        (lambda value: value["routes"].__setitem__("predict", "http://wrong/predict"), "predictor routes"),
        (lambda value: value["revision_annotations"].__setitem__("autoscaling.knative.dev/class", "hpa.autoscaling.knative.dev"), "Revision"),
        (lambda value: value["timeouts"].__setitem__("ingress_seconds", 30), "timeout chain"),
        (lambda value: value["autoscaler"].__setitem__("enable-scale-to-zero", "false"), "scale-to-zero"),
    ),
)
def test_preflight_rejects_missing_incompatible_or_unsafe_state(mutation, message) -> None:
    _, candidate = qualified()
    value = snapshot(candidate)
    mutation(value)
    with pytest.raises(ValueError, match=message):
        validate_runtime_snapshot(value, candidate)
