"""Validate Kubernetes documents against one core OpenAPI file and exact CRDs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft4Validator


def _identity(group: str, version: str, kind: str) -> tuple[str, str]:
    return ((f"{group}/{version}" if group else version), kind)


def load_schemas(core_path: Path, crd_paths: list[Path]) -> dict[tuple[str, str], dict]:
    swagger = json.loads(core_path.read_text())
    definitions = copy.deepcopy(swagger["definitions"])
    for name, definition in definitions.items():
        if name.endswith(".IntOrString"):
            definition["type"] = ["integer", "string"]

    schemas: dict[tuple[str, str], dict] = {}
    for name, definition in definitions.items():
        for gvk in definition.get("x-kubernetes-group-version-kind", []):
            schemas[_identity(gvk["group"], gvk["version"], gvk["kind"])] = {
                "$ref": f"#/definitions/{name}",
                "definitions": definitions,
            }

    for path in crd_paths:
        for document in yaml.safe_load_all(path.read_text()):
            if not isinstance(document, dict) or document.get("kind") != "CustomResourceDefinition":
                continue
            spec = document["spec"]
            for version in spec["versions"]:
                schema = version.get("schema", {}).get("openAPIV3Schema")
                if schema:
                    schemas[_identity(spec["group"], version["name"], spec["names"]["kind"])] = schema
    return schemas


def validate_documents(schemas: dict[tuple[str, str], dict], paths: list[Path]) -> dict[str, Any]:
    checked: dict[str, int] = {}
    uncovered: set[str] = set()
    errors: list[dict[str, str]] = []
    for path in paths:
        for document in yaml.safe_load_all(path.read_text()):
            if not isinstance(document, dict) or not document.get("apiVersion") or not document.get("kind"):
                continue
            identity = (document["apiVersion"], document["kind"])
            label = "/".join(identity)
            schema = schemas.get(identity)
            if schema is None:
                uncovered.add(label)
                continue
            checked[label] = checked.get(label, 0) + 1
            name = document.get("metadata", {}).get("name", "<unnamed>")
            for error in Draft4Validator(schema).iter_errors(document):
                errors.append({
                    "resource": f"{label}/{name}",
                    "path": "/".join(str(item) for item in error.absolute_path),
                    "message": error.message,
                })
    return {
        "status": "FAIL" if errors or uncovered else "PASS_OFFLINE",
        "checked": checked,
        "checked_count": sum(checked.values()),
        "uncovered": sorted(uncovered),
        "errors": errors,
        "scope": "structural OpenAPI only; CEL, admission, reconciliation, and runtime are unverified",
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--crd", type=Path, action="append", default=[])
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = validate_documents(load_schemas(args.core, args.crd), args.manifest)
    report["schemas"] = [
        {"path": str(path), "sha256": _sha256(path)}
        for path in [args.core, *args.crd]
    ]
    report["manifests"] = [
        {"path": str(path), "sha256": _sha256(path)} for path in args.manifest
    ]
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["status"] == "PASS_OFFLINE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
