from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
import scripts.c11_runtime_preflight as preflight

from scripts.c11_runtime_preflight import (
    REQUIRED_CONTROLLERS,
    REQUIRED_IMAGES,
    assess,
    controller_matrix_qualified,
    kubectl_command,
    qualify_image_ledger,
    validate_image_ledger,
    validate_target,
)


def plan(tmp_path: Path) -> Path:
    value = {
        "cluster_name": "cogniflow-c11-isolated",
        "context": "kind-cogniflow-c11-isolated",
        "option": "dedicated_kind",
        "owner_authorization": False,
        "kubeconfig": str(tmp_path / "missing-kubeconfig"),
        "qualified_kubectl": str(tmp_path / "missing-kubectl"),
        "qualified_cosign": None,
        "qualified_cosign_sha256": None,
        "qualified_trivy": None,
        "qualified_trivy_sha256": None,
        "cosign_certificate_identity_regexp": "",
        "image_ledger": None,
        "controller_matrix": None,
        "storage_qualified": False,
        "minimum_available_memory_bytes": 12 * 1024**3,
        "minimum_disk_bytes": 60 * 1024**3,
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(value))
    return path


@pytest.mark.parametrize(
    ("cluster", "context"),
    [
        ("cogniflow-local", "kind-cogniflow-local"),
        ("cogniflow-module1-qualification", "kind-cogniflow-module1-qualification"),
        ("other", "kind-other"),
        ("cogniflow-c11-safe", "kind-wrong"),
    ],
)
def test_protected_or_ambiguous_target_is_rejected(cluster: str, context: str) -> None:
    with pytest.raises(ValueError):
        validate_target(cluster, context)


def test_missing_authorization_runtime_and_security_evidence_is_blocked(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    result = assess(plan(tmp_path), output)
    assert result["status"] == "BLOCKED"
    assert result["mutation_executed"] is False
    assert {"owner_authorization", "images", "controller_matrix", "storage", "kubeconfig"} <= set(
        result["blockers"]
    )
    assert output.stat().st_mode & 0o777 == 0o600


def test_resource_requirements_cannot_be_weakened(tmp_path: Path) -> None:
    path = plan(tmp_path)
    value = json.loads(path.read_text())
    value["minimum_available_memory_bytes"] = 6 * 1024**3
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="12 GiB"):
        assess(path, tmp_path / "result.json")


def test_kubectl_requires_explicit_safe_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="kubectl"):
        kubectl_command(tmp_path / "missing", tmp_path / "missing-config", "kind-cogniflow-c11-safe")
    binary = tmp_path / "kubectl"
    binary.write_text("fixture")
    binary.chmod(0o700)
    config = tmp_path / "config"
    config.write_text("fixture")
    command = kubectl_command(binary, config, "kind-cogniflow-c11-safe", "get", "nodes")
    assert command == [
        str(binary), "--kubeconfig", str(config), "--context", "kind-cogniflow-c11-safe",
        "get", "nodes",
    ]


def image_ledger(tmp_path: Path, sbom_sha256: str = "b" * 64) -> Path:
    item = {
        "reference": "registry.example/cogniflow/image@sha256:" + "a" * 64,
        "signature_verified": True,
        "scan": {"complete": True, "high": 0, "critical": 0},
        "sbom_sha256": sbom_sha256,
        "provenance_sha256": "c" * 64,
    }
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({name: item for name in REQUIRED_IMAGES}))
    return ledger


def test_image_ledger_schema_requires_every_claimed_identity(tmp_path: Path) -> None:
    ledger = image_ledger(tmp_path)
    validate_image_ledger(ledger)
    value = json.loads(ledger.read_text())
    value["kserve-controller"]["scan"]["high"] = 1
    ledger.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="kserve-controller"):
        validate_image_ledger(ledger)


def attestation(reference: str, predicate_type: str) -> tuple[str, str]:
    payload = json.dumps({
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": reference.split("@", 1)[0], "digest": {
            "sha256": reference.rsplit(":", 1)[1]
        }}],
        "predicateType": predicate_type,
        "predicate": {},
    }, sort_keys=True).encode()
    envelope = json.dumps({"payload": base64.b64encode(payload).decode()})
    return envelope, hashlib.sha256(payload).hexdigest()


def test_qualification_rejects_claims_not_backed_by_verified_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = "registry.example/cogniflow/image@sha256:" + "a" * 64
    sbom, sbom_digest = attestation(reference, "https://spdx.dev/Document")
    provenance, provenance_digest = attestation(reference, "https://slsa.dev/provenance/v1")
    ledger = image_ledger(tmp_path, sbom_digest)
    contents = json.loads(ledger.read_text())
    for item in contents.values():
        item["provenance_sha256"] = provenance_digest
    ledger.write_text(json.dumps(contents))
    cosign = tmp_path / "cosign"
    trivy = tmp_path / "trivy"
    for tool in (cosign, trivy):
        tool.write_text("tool")
        tool.chmod(0o700)

    def verified_output(binary: Path, *arguments: str) -> str:
        if arguments == ("version",):
            return "GitVersion:    v3.1.4"
        if arguments == ("--version",):
            return "Version: 0.76.2"
        if arguments[0] == "verify-attestation":
            return sbom if "spdxjson" in arguments else provenance
        if binary == trivy:
            return json.dumps({"ArtifactName": reference, "Results": []})
        return "verified signature"

    monkeypatch.setattr(preflight, "_run", verified_output)
    qualify_image_ledger(
        ledger, cosign, hashlib.sha256(cosign.read_bytes()).hexdigest(),
        trivy, hashlib.sha256(trivy.read_bytes()).hexdigest(), "^trusted-workflow$",
    )

    contents = json.loads(ledger.read_text())
    contents["kfp-api"]["sbom_sha256"] = "d" * 64
    ledger.write_text(json.dumps(contents))
    with pytest.raises(ValueError, match="evidence digest mismatch"):
        qualify_image_ledger(
            ledger, cosign, hashlib.sha256(cosign.read_bytes()).hexdigest(),
            trivy, hashlib.sha256(trivy.read_bytes()).hexdigest(), "^trusted-workflow$",
        )


def test_qualification_uses_actual_scan_not_zero_count_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = "registry.example/cogniflow/image@sha256:" + "a" * 64
    sbom, sbom_digest = attestation(reference, "https://spdx.dev/Document")
    provenance, provenance_digest = attestation(reference, "https://slsa.dev/provenance/v1")
    ledger = image_ledger(tmp_path, sbom_digest)
    contents = json.loads(ledger.read_text())
    for item in contents.values():
        item["provenance_sha256"] = provenance_digest
    ledger.write_text(json.dumps(contents))
    cosign = tmp_path / "cosign"
    trivy = tmp_path / "trivy"
    for tool in (cosign, trivy):
        tool.write_text("tool")
        tool.chmod(0o700)

    def vulnerable_scan(binary: Path, *arguments: str) -> str:
        if arguments == ("version",):
            return "GitVersion:    v3.1.4"
        if arguments == ("--version",):
            return "Version: 0.76.2"
        if arguments[0] == "verify-attestation":
            return sbom if "spdxjson" in arguments else provenance
        if binary == trivy:
            return json.dumps({
                "ArtifactName": reference,
                "Results": [{"Vulnerabilities": [{"Severity": "HIGH"}]}],
            })
        return "verified signature"

    monkeypatch.setattr(preflight, "_run", vulnerable_scan)
    with pytest.raises(ValueError, match="HIGH/CRITICAL"):
        qualify_image_ledger(
            ledger, cosign, hashlib.sha256(cosign.read_bytes()).hexdigest(),
            trivy, hashlib.sha256(trivy.read_bytes()).hexdigest(), "^trusted-workflow$",
        )


def test_controller_matrix_requires_every_qualified_component(tmp_path: Path) -> None:
    item = {"version": "1.0", "qualified": True, "source": "https://example.invalid/release"}
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"components": {name: item for name in REQUIRED_CONTROLLERS}}))
    assert controller_matrix_qualified(matrix) is True
    value = json.loads(matrix.read_text())
    value["components"]["kserve"]["qualified"] = False
    matrix.write_text(json.dumps(value))
    assert controller_matrix_qualified(matrix) is False
