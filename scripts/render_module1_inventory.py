"""Inventory immutable rendered manifests for Module I qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resource_identity(document: dict[str, Any]) -> dict[str, str]:
    metadata = document.get("metadata", {})
    return {
        "apiVersion": str(document.get("apiVersion", "")),
        "kind": str(document.get("kind", "")),
        "namespace": str(metadata.get("namespace", "")),
        "name": str(metadata.get("name", "")),
    }


def build_inventory(commit: str, manifests: dict[str, Path]) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("source commit must be an exact Git SHA")
    rendered: dict[str, str] = {}
    resources: list[dict[str, str]] = []
    for component, path in sorted(manifests.items()):
        data = path.read_bytes()
        rendered[component] = sha256(data)
        for document in yaml.safe_load_all(data):
            if isinstance(document, dict):
                identity = resource_identity(document)
                if not all((identity["apiVersion"], identity["kind"], identity["name"])):
                    raise ValueError(f"rendered resource identity is incomplete: {component}")
                resources.append(identity)
    resources.sort(key=lambda value: tuple(value.values()))
    encoded = json.dumps(resources, separators=(",", ":"), sort_keys=True).encode()
    return {
        "method": "kustomize",
        "source_commit": commit,
        "rendered_manifests": rendered,
        "resource_identities": resources,
        "resource_identities_sha256": sha256(encoded),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("manifest", nargs="+")
    args = parser.parse_args()
    manifests = {}
    for value in args.manifest:
        component, separator, path = value.partition("=")
        if not separator or not component or component in manifests:
            raise SystemExit("manifests must be unique COMPONENT=PATH values")
        manifests[component] = Path(path)
    args.output.write_text(json.dumps(build_inventory(args.commit, manifests), indent=2) + "\n")


if __name__ == "__main__":
    main()
