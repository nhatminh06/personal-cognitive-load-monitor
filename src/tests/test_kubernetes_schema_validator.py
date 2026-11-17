from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validate_kubernetes_schemas import load_schemas, validate_documents


def test_schema_validator_rejects_invalid_and_uncovered_resources(tmp_path: Path) -> None:
    core = tmp_path / "core.json"
    core.write_text(json.dumps({
        "definitions": {
            "io.k8s.api.core.v1.Service": {
                "type": "object",
                "required": ["apiVersion", "kind", "metadata", "spec"],
                "properties": {
                    "apiVersion": {"type": "string"},
                    "kind": {"type": "string"},
                    "metadata": {"type": "object"},
                    "spec": {"type": "object", "required": ["ports"]},
                },
                "x-kubernetes-group-version-kind": [
                    {"group": "", "version": "v1", "kind": "Service"}
                ],
            }
        }
    }))
    manifests = tmp_path / "manifests.yaml"
    manifests.write_text(yaml.safe_dump_all([
        {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "invalid"}, "spec": {}},
        {"apiVersion": "example.test/v1", "kind": "Unknown", "metadata": {"name": "unknown"}},
    ]))

    report = validate_documents(load_schemas(core, []), [manifests])

    assert report["status"] == "FAIL"
    assert report["errors"][0]["path"] == "spec"
    assert report["uncovered"] == ["example.test/v1/Unknown"]


def test_schema_validator_uses_matching_crd_schema(tmp_path: Path) -> None:
    core = tmp_path / "core.json"
    core.write_text('{"definitions": {}}')
    crd = tmp_path / "crd.yaml"
    crd.write_text(yaml.safe_dump({
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "spec": {
            "group": "example.test",
            "names": {"kind": "Example", "plural": "examples"},
            "versions": [{
                "name": "v1",
                "schema": {"openAPIV3Schema": {
                    "type": "object",
                    "required": ["spec"],
                    "properties": {"spec": {"type": "object"}},
                }},
            }],
        },
    }))
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({
        "apiVersion": "example.test/v1",
        "kind": "Example",
        "metadata": {"name": "valid"},
        "spec": {},
    }))

    report = validate_documents(load_schemas(core, [crd]), [manifest])

    assert report["status"] == "PASS_OFFLINE"
    assert report["checked"] == {"example.test/v1/Example": 1}
