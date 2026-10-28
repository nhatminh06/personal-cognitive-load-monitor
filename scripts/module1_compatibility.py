"""Fail-closed offline qualification and runtime-snapshot checks for Module I."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUIRED_CRDS = {
    "certificaterequests.cert-manager.io",
    "certificates.cert-manager.io",
    "certificates.networking.internal.knative.dev",
    "challenges.acme.cert-manager.io",
    "clusterdomainclaims.networking.internal.knative.dev",
    "clusterissuers.cert-manager.io",
    "clusterservingruntimes.serving.kserve.io",
    "clusterstoragecontainers.serving.kserve.io",
    "inferenceservices.serving.kserve.io",
    "configurations.serving.knative.dev",
    "revisions.serving.knative.dev",
    "domainmappings.serving.knative.dev",
    "images.caching.internal.knative.dev",
    "inferencegraphs.serving.kserve.io",
    "inferencemodelrewrites.llm-d.ai",
    "inferenceobjectives.llm-d.ai",
    "inferencepools.inference.networking.k8s.io",
    "inferencepools.inference.networking.x-k8s.io",
    "ingresses.networking.internal.knative.dev",
    "issuers.cert-manager.io",
    "kernelcachecaptures.serving.kserve.io",
    "kernelcachenodegroups.serving.kserve.io",
    "kernelcachenodes.serving.kserve.io",
    "kernelcaches.serving.kserve.io",
    "llminferenceserviceconfigs.serving.kserve.io",
    "llminferenceservices.serving.kserve.io",
    "localmodelcaches.serving.kserve.io",
    "localmodelnamespacecaches.serving.kserve.io",
    "localmodelnodegroups.serving.kserve.io",
    "localmodelnodes.serving.kserve.io",
    "metrics.autoscaling.internal.knative.dev",
    "orders.acme.cert-manager.io",
    "podautoscalers.autoscaling.internal.knative.dev",
    "routes.serving.knative.dev",
    "serverlessservices.networking.internal.knative.dev",
    "services.serving.knative.dev",
    "servingruntimes.serving.kserve.io",
    "trainedmodels.serving.kserve.io",
}
REQUIRED_CONTROLLERS = {
    "kserve/kserve-controller-manager",
    "kserve/kserve-localmodel-controller-manager",
    "kserve/llmisvc-controller-manager",
    "knative-serving/controller",
    "knative-serving/autoscaler",
    "knative-serving/activator",
    "knative-serving/webhook",
    "knative-serving/net-istio-controller",
    "knative-serving/net-istio-webhook",
    "istio-system/istiod",
    "istio-system/istio-ingressgateway",
    "kube-system/istio-cni-node",
    "cert-manager/cert-manager",
    "cert-manager/cert-manager-webhook",
    "cert-manager/cert-manager-cainjector",
}
DIGEST_IMAGE = re.compile(r"[^\s]+@sha256:[a-f0-9]{64}")
KUBERNETES_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].+)?$")


def kubernetes_version_matches(policy: dict[str, Any], actual: str) -> bool:
    """Match exact patches, or an explicitly bounded patch range."""
    match = KUBERNETES_VERSION.fullmatch(actual)
    if not match or ("-gke." in actual and policy.get("gke_accepted") is not True):
        return False
    actual_core = tuple(map(int, match.groups()))
    if policy.get("policy") == "exact":
        return actual == policy.get("version")
    if policy.get("policy") == "patch_range":
        if "-gke." in actual:
            return False
        minimum = KUBERNETES_VERSION.fullmatch(str(policy.get("minimum", "")))
        maximum = KUBERNETES_VERSION.fullmatch(str(policy.get("maximum", "")))
        return bool(
            minimum
            and maximum
            and tuple(map(int, minimum.groups())) <= actual_core <= tuple(map(int, maximum.groups()))
        )
    return False


def validate_matrix(matrix: dict[str, Any], *, require_qualified: bool = False) -> None:
    candidates = matrix.get("candidates")
    if matrix.get("qualification_status") not in {"BLOCKED", "QUALIFIED"} or not isinstance(candidates, list):
        raise ValueError("compatibility matrix status or candidates are invalid")
    ids = [candidate.get("id") for candidate in candidates]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError("compatibility candidate IDs must be unique")
    required = {
        "id", "kserve", "knative_serving", "kubernetes", "networking", "cert_manager",
        "support_status", "integration_evidence", "security_findings", "suitable", "evidence",
        "source", "approved_inventory",
    }
    for candidate in candidates:
        if set(candidate) != required or not candidate["evidence"] or any(
            not str(url).startswith("https://") for url in candidate["evidence"]
        ):
            raise ValueError(f"compatibility candidate is incomplete: {candidate.get('id', 'unknown')}")
        kubernetes = candidate["kubernetes"]
        if not isinstance(kubernetes, dict) or not any(
            kubernetes_version_matches(kubernetes, version)
            for version in (
                str(kubernetes.get("version", "")),
                str(kubernetes.get("minimum", "")),
            )
        ):
            raise ValueError(f"Kubernetes qualification policy is invalid: {candidate['id']}")
    selected = matrix.get("selected_candidate")
    selected_rows = [candidate for candidate in candidates if candidate["id"] == selected]
    inventory = selected_rows[0].get("approved_inventory", {}) if selected_rows else {}
    qualified = (
        matrix["qualification_status"] == "QUALIFIED"
        and len(selected_rows) == 1
        and selected_rows[0]["suitable"] is True
        and selected_rows[0]["support_status"] == "qualified"
        and re.fullmatch(r"[a-f0-9]{40}", selected_rows[0]["source"].get("commit", "")) is not None
        and set(inventory.get("crds", [])) == REQUIRED_CRDS
        and set(inventory.get("controllers", {})) == REQUIRED_CONTROLLERS
        and all(
            isinstance(images, list)
            and images
            and all(DIGEST_IMAGE.fullmatch(image) for image in images)
            for images in inventory.get("controllers", {}).values()
        )
        and inventory.get("installation", {}).get("method") == "kustomize"
        and inventory.get("configuration")
    )
    if matrix["qualification_status"] == "QUALIFIED" and not qualified:
        raise ValueError("QUALIFIED requires one suitable selected candidate")
    if require_qualified and not qualified:
        raise ValueError("Module I compatibility is BLOCKED pending exact integration qualification")


def validate_control_plane_snapshot(snapshot: dict[str, Any], candidate: dict[str, Any]) -> None:
    expected = {
        "kserve": candidate["kserve"],
        "knative_serving": candidate["knative_serving"],
        "networking": candidate["networking"],
        "cert_manager": candidate["cert_manager"],
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise ValueError("runtime versions do not match the qualified matrix")
    if not kubernetes_version_matches(candidate["kubernetes"], str(snapshot.get("kubernetes", ""))):
        raise ValueError("Kubernetes patch does not match the qualified policy")
    approved = candidate.get("approved_inventory", {})
    if set(snapshot.get("crds", [])) != set(approved.get("crds", [])):
        raise ValueError("required KServe/Knative CRD inventory does not match")
    controllers = snapshot.get("controllers", {})
    actual_images = {name: value.get("images") for name, value in controllers.items()}
    if set(controllers) != REQUIRED_CONTROLLERS or any(value.get("available") is not True for value in controllers.values()):
        raise ValueError("controller inventory must be complete, available and digest-pinned")
    if actual_images != approved.get("controllers"):
        raise ValueError("controller image inventory does not match the approved matrix")
    if snapshot.get("configuration") != approved.get("configuration"):
        raise ValueError("effective serving configuration does not match the approved matrix")


def validate_runtime_snapshot(snapshot: dict[str, Any], candidate: dict[str, Any]) -> None:
    validate_control_plane_snapshot(snapshot, candidate)
    if snapshot.get("installation") != candidate.get("approved_inventory", {}).get("installation"):
        raise ValueError("rendered installation evidence does not match the approved matrix")
    revision = snapshot.get("revision_annotations", {})
    if revision != {
        "autoscaling.knative.dev/class": "kpa.autoscaling.knative.dev",
        "autoscaling.knative.dev/min-scale": "0",
        "autoscaling.knative.dev/max-scale": "3",
        "autoscaling.knative.dev/target": "1",
    }:
        raise ValueError("effective Revision autoscaling annotations do not match")
    routes = snapshot.get("routes", {})
    model = snapshot.get("model_name")
    namespace = snapshot.get("namespace")
    origin = f"http://{model}-predictor.{namespace}.svc.cluster.local"
    if routes != {
        "origin": origin,
        "predict": f"{origin}/v1/models/{model}:predict",
        "metadata": f"{origin}/v1/models/{model}/metadata",
    }:
        raise ValueError("KServe predictor routes do not match the internal service contract")
    acceptance = snapshot.get("acceptance", {})
    expected_states = [
        "READY",
        "INITIAL_INFERENCE",
        "SCALED_TO_ZERO",
        "COLD_ACTIVATION_READY",
        "POST_ACTIVATION_INFERENCE",
    ]
    if (
        acceptance.get("status") != "PASS"
        or acceptance.get("states") != expected_states
        or not isinstance(acceptance.get("cold_activation_seconds"), int)
        or acceptance["cold_activation_seconds"] < 0
        or acceptance["cold_activation_seconds"] > acceptance.get("cold_activation_deadline_seconds", -1)
    ):
        raise ValueError("scale-to-zero acceptance sequence is incomplete or exceeded its deadline")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--require-qualified", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--control-plane-snapshot", type=Path)
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text())
    validate_matrix(matrix, require_qualified=args.require_qualified)
    if args.snapshot:
        selected = next(row for row in matrix["candidates"] if row["id"] == matrix["selected_candidate"])
        validate_runtime_snapshot(json.loads(args.snapshot.read_text()), selected)
    if args.control_plane_snapshot:
        selected = next(row for row in matrix["candidates"] if row["id"] == matrix["selected_candidate"])
        validate_control_plane_snapshot(json.loads(args.control_plane_snapshot.read_text()), selected)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, StopIteration, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
