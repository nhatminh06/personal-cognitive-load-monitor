"""Reconcile pinned upstream KServe dependencies before any cluster mutation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from scripts.module1_compatibility import REQUIRED_CONTROLLERS, REQUIRED_CRDS

UPSTREAM_CONTROL_PLANE_ALLOW_POLICIES = {
    "istio-system/cluster-local-gateway",
    "istio-system/istio-ingressgateway",
    "knative-serving/activator-service",
    "knative-serving/autoscaler",
    "knative-serving/controller",
    "knative-serving/istio-webhook",
    "knative-serving/webhook",
}


def verify(documents: list[dict[str, Any]]) -> dict[str, Any]:
    workloads = {
        f"{document.get('metadata', {}).get('namespace', 'default')}/{document.get('metadata', {}).get('name')}"
        for document in documents
        if document.get("kind") in {"Deployment", "DaemonSet"}
    }
    crds = {
        document.get("metadata", {}).get("name")
        for document in documents
        if document.get("kind") == "CustomResourceDefinition"
    }
    if not REQUIRED_CONTROLLERS <= workloads:
        raise ValueError(f"required rendered workloads are missing: {sorted(REQUIRED_CONTROLLERS - workloads)}")
    relevant_crds = {name for name in crds if name in REQUIRED_CRDS}
    if relevant_crds != REQUIRED_CRDS:
        raise ValueError(f"required rendered CRDs are missing: {sorted(REQUIRED_CRDS - relevant_crds)}")
    if "kserve/kserve-localmodelnode-agent" in workloads:
        raise ValueError("disabled local-model node agent is unexpectedly rendered")
    allow_policies = set()
    for document in documents:
        if document.get("kind") != "AuthorizationPolicy":
            continue
        spec = document.get("spec", {})
        if spec.get("action", "ALLOW") == "ALLOW" and any(not rule for rule in spec.get("rules", [])):
            metadata = document.get("metadata", {})
            identity = f"{metadata.get('namespace', 'default')}/{metadata.get('name')}"
            allow_policies.add(identity)
    if allow_policies - UPSTREAM_CONTROL_PLANE_ALLOW_POLICIES:
        raise ValueError(f"unapproved allow-all AuthorizationPolicy: {sorted(allow_policies - UPSTREAM_CONTROL_PLANE_ALLOW_POLICIES)}")
    return {
        "workloads": sorted(REQUIRED_CONTROLLERS),
        "crds": sorted(relevant_crds),
        "upstream_control_plane_allow_policies": sorted(allow_policies),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("manifest", nargs="+")
    args = parser.parse_args()
    documents: list[dict[str, Any]] = []
    for path in map(Path, args.manifest):
        documents.extend(document for document in yaml.safe_load_all(path.read_bytes()) if isinstance(document, dict))
    args.output.write_text(json.dumps(verify(documents), indent=2) + "\n")


if __name__ == "__main__":
    main()
