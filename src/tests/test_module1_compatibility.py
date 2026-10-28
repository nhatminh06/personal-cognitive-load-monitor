from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.module1_compatibility import (
    REQUIRED_CONTROLLERS,
    REQUIRED_CRDS,
    kubernetes_version_matches,
    validate_matrix,
    validate_runtime_snapshot,
)


ROOT = Path(__file__).parents[2]
MATRIX = json.loads((ROOT / "docs/module1/compatibility-matrix.json").read_text())


def qualified() -> tuple[dict, dict]:
    matrix = deepcopy(MATRIX)
    candidate = matrix["candidates"][-1]
    candidate["support_status"] = "qualified"
    candidate["integration_evidence"] = "isolated exact-matrix acceptance evidence"
    candidate["suitable"] = True
    digest = "a" * 64
    candidate["approved_inventory"] = {
        "crds": sorted(REQUIRED_CRDS),
        "controllers": {
            name: [f"registry.example/{name.replace('/', '-')}@sha256:{digest}"]
            for name in REQUIRED_CONTROLLERS
        },
        "installation": {
            "method": "kustomize",
            "source_commit": candidate["source"]["commit"],
            "rendered_manifests": {"kserve": "b" * 64},
            "resource_identities_sha256": "c" * 64,
        },
        "configuration": {
            "autoscaler": {"enable-scale-to-zero": "true", "stable-window": "60s", "scale-to-zero-grace-period": "30s"},
            "defaults": {"revision-timeout-seconds": "35", "revision-response-start-timeout-seconds": "35", "revision-idle-timeout-seconds": "35"},
        },
    }
    matrix["qualification_status"] = "QUALIFIED"
    matrix["selected_candidate"] = candidate["id"]
    return matrix, candidate


def snapshot(candidate: dict) -> dict:
    digest = "a" * 64
    controllers = {
        name: {
            "available": True,
            "images": [f"registry.example/{name.replace('/', '-')}@sha256:{digest}"],
        }
        for name in REQUIRED_CONTROLLERS
    }
    origin = "http://cognitive-load-classifier-predictor.cogniflow.svc.cluster.local"
    return {
        "kserve": candidate["kserve"], "knative_serving": candidate["knative_serving"],
        "kubernetes": candidate["kubernetes"]["version"], "networking": candidate["networking"],
        "cert_manager": candidate["cert_manager"], "namespace": "cogniflow",
        "model_name": "cognitive-load-classifier",
        "crds": candidate["approved_inventory"]["crds"],
        "controllers": controllers,
        "installation": deepcopy(candidate["approved_inventory"]["installation"]),
        "configuration": deepcopy(candidate["approved_inventory"]["configuration"]),
        "revision_annotations": {
            "autoscaling.knative.dev/class": "kpa.autoscaling.knative.dev",
            "autoscaling.knative.dev/min-scale": "0", "autoscaling.knative.dev/max-scale": "3",
            "autoscaling.knative.dev/target": "1",
        },
        "routes": {"origin": origin, "predict": f"{origin}/v1/models/cognitive-load-classifier:predict",
                   "metadata": f"{origin}/v1/models/cognitive-load-classifier/metadata"},
        "acceptance": {
            "status": "PASS",
            "states": ["READY", "INITIAL_INFERENCE", "SCALED_TO_ZERO", "COLD_ACTIVATION_READY", "POST_ACTIVATION_INFERENCE"],
            "cold_activation_seconds": 20,
            "cold_activation_deadline_seconds": 35,
        },
    }


def test_kubernetes_exact_patch_does_not_accept_other_kind_or_gke_patches() -> None:
    policy = {"policy": "exact", "version": "1.34.11", "gke_accepted": False}
    assert kubernetes_version_matches(policy, "1.34.11")
    assert not kubernetes_version_matches(policy, "1.34.12")
    assert not kubernetes_version_matches(policy, "1.34.11-gke.100")
    gke_policy = {"policy": "exact", "version": "1.34.11-gke.100", "gke_accepted": True}
    assert kubernetes_version_matches(gke_policy, "1.34.11-gke.100")


@pytest.mark.parametrize(
    ("version", "accepted"),
    (("1.34.10", True), ("1.34.12", True), ("1.34.9", False), ("1.34.13", False), ("1.35.0", False)),
)
def test_explicit_kubernetes_patch_range_boundaries(version: str, accepted: bool) -> None:
    policy = {"policy": "patch_range", "minimum": "1.34.10", "maximum": "1.34.12", "gke_accepted": False}
    assert kubernetes_version_matches(policy, version) is accepted


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
        (lambda value: value["installation"].__setitem__("source_commit", "b" * 40), "installation evidence"),
        (lambda value: value["installation"]["rendered_manifests"].__setitem__("kserve", "d" * 64), "installation evidence"),
        (lambda value: value.__setitem__("kubernetes", "1.34.12"), "Kubernetes patch"),
        (lambda value: value.__setitem__("knative_serving", "1.21.1"), "runtime versions"),
        (lambda value: value["routes"].__setitem__("predict", "http://wrong/predict"), "predictor routes"),
        (lambda value: value["revision_annotations"].__setitem__("autoscaling.knative.dev/class", "hpa.autoscaling.knative.dev"), "Revision"),
        (lambda value: value["configuration"]["defaults"].__setitem__("revision-timeout-seconds", "30"), "configuration"),
        (lambda value: value["configuration"]["autoscaler"].__setitem__("enable-scale-to-zero", "false"), "configuration"),
        (lambda value: value["acceptance"].__setitem__("cold_activation_seconds", 36), "scale-to-zero"),
    ),
)
def test_preflight_rejects_missing_incompatible_or_unsafe_state(mutation, message) -> None:
    _, candidate = qualified()
    value = snapshot(candidate)
    mutation(value)
    with pytest.raises(ValueError, match=message):
        validate_runtime_snapshot(value, candidate)
