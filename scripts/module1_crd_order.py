"""Apply mixed CRD manifests only after their APIs are established and discoverable."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


CONTRACTS = {
    "knative": (
        ("caching.internal.knative.dev", "v1alpha1", "Image"),
        ("networking.internal.knative.dev", "v1alpha1", "Certificate"),
    ),
    "kserve": (
        ("serving.kserve.io", "v1alpha1", "ClusterServingRuntime"),
        ("serving.kserve.io", "v1alpha1", "ClusterStorageContainer"),
    ),
}
Runner = Callable[..., subprocess.CompletedProcess[str]]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(document: dict[str, Any]) -> dict[str, str]:
    metadata = document.get("metadata", {})
    return {
        "apiVersion": str(document.get("apiVersion", "")),
        "kind": str(document.get("kind", "")),
        "namespace": str(metadata.get("namespace", "")),
        "name": str(metadata.get("name", "")),
    }


def split_manifest(manifest: Path, component: str, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True)
    original = manifest.read_bytes()
    documents = [document for document in yaml.safe_load_all(original) if isinstance(document, dict)]
    crds = [document for document in documents if document.get("kind") == "CustomResourceDefinition"]
    resources = [document for document in documents if document.get("kind") != "CustomResourceDefinition"]
    contracts = CONTRACTS[component]
    required = []
    for group, version, kind in contracts:
        matches = [
            document for document in crds
            if document.get("spec", {}).get("group") == group
            and document.get("spec", {}).get("names", {}).get("kind") == kind
        ]
        if len(matches) != 1:
            raise ValueError(f"{component} requires exactly one CRD for {group}/{kind}")
        crd = matches[0]
        versions = {item.get("name"): item.get("served") for item in crd.get("spec", {}).get("versions", [])}
        if versions.get(version) is not True:
            raise ValueError(f"{crd['metadata']['name']} does not serve {version}")
        dependents = [
            identity(document) for document in resources
            if document.get("apiVersion") == f"{group}/{version}" and document.get("kind") == kind
        ]
        if not dependents:
            raise ValueError(f"{component} has no dependent {group}/{version}/{kind} resources")
        required.append({
            "group": group,
            "version": version,
            "kind": kind,
            "crd": crd["metadata"]["name"],
            "dependents": dependents,
        })
    crd_bytes = yaml.safe_dump_all(crds, explicit_start=True, sort_keys=False).encode()
    resource_bytes = yaml.safe_dump_all(resources, explicit_start=True, sort_keys=False).encode()
    (output_dir / "crds.yaml").write_bytes(crd_bytes)
    (output_dir / "resources.yaml").write_bytes(resource_bytes)
    evidence = {
        "component": component,
        "original": {"path": str(manifest), "sha256": sha256(original), "resources": list(map(identity, documents))},
        "crds": {
            "sha256": sha256(crd_bytes),
            "resources": list(map(identity, crds)),
            "expected": [
                {
                    "name": document["metadata"]["name"],
                    "served_versions": [
                        version["name"] for version in document.get("spec", {}).get("versions", [])
                        if version.get("served") is True
                    ],
                }
                for document in crds
            ],
        },
        "resources": {"sha256": sha256(resource_bytes), "resources": list(map(identity, resources))},
        "required_apis": required,
    }
    (output_dir / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def apply_staged(
    *, context: str, manifest: Path, component: str, output_dir: Path,
    server_side: bool = False, runner: Runner = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep, discovery_attempts: int = 30,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"staged apply evidence already exists: {output_dir}")
    apply = ["kubectl", "--context", context, "apply"]
    if server_side:
        apply += ["--server-side", "--force-conflicts"]
    try:
        evidence = split_manifest(manifest, component, output_dir)
        runner([*apply, "-f", str(output_dir / "crds.yaml")], check=True, text=True, capture_output=True)
        for expected in evidence["crds"]["expected"]:
            runner(
                ["kubectl", "--context", context, "wait", "--for=condition=Established",
                 f"crd/{expected['name']}", "--timeout=180s"],
                check=True, text=True, capture_output=True,
            )
            api_result = runner(
                ["kubectl", "--context", context, "get", "crd", expected["name"], "-o", "json"],
                check=True, text=True, capture_output=True,
            )
            live = json.loads(api_result.stdout)
            established = any(
                condition.get("type") == "Established" and condition.get("status") == "True"
                for condition in live.get("status", {}).get("conditions", [])
            )
            live_served = {
                version.get("name") for version in live.get("spec", {}).get("versions", [])
                if version.get("served") is True
            }
            if not established or not set(expected["served_versions"]).issubset(live_served):
                raise RuntimeError(f"live CRD is not Established or served: {expected['name']}")
        for group, version in sorted({(item["group"], item["version"]) for item in evidence["required_apis"]}):
            for attempt in range(discovery_attempts):
                discovery_result = runner(
                    ["kubectl", "--context", context, "get", "--raw", f"/apis/{group}/{version}"],
                    check=False, text=True, capture_output=True,
                )
                if discovery_result.returncode == 0:
                    break
                if attempt + 1 == discovery_attempts:
                    raise RuntimeError(f"API discovery timed out: {group}/{version}")
                sleeper(1)
        runner([*apply, "-f", str(output_dir / "resources.yaml")], check=True, text=True, capture_output=True)
    except Exception as error:
        (output_dir / "result.json").write_text(
            json.dumps({"status": "FAIL", "error": str(error)}, indent=2) + "\n"
        )
        raise
    outcome = {"status": "PASS", "verified_apis": evidence["required_apis"]}
    (output_dir / "result.json").write_text(json.dumps(outcome, indent=2) + "\n")
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--context", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--component", choices=sorted(CONTRACTS), required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--server-side", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        raise SystemExit("staged apply requires explicit --execute authorization")
    apply_staged(
        context=args.context,
        manifest=args.manifest,
        component=args.component,
        output_dir=args.evidence_dir,
        server_side=args.server_side,
    )


if __name__ == "__main__":
    main()
