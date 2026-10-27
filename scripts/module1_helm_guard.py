"""Fail closed before Module I can mutate the shared Helm release."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

RELEASE = "cognitive-load-monitor"
NAMESPACE = "cogniflow"
OWNERS = {"module3-standard": "Standard", "module1-knative": "Knative"}


def validate_target(actual_context: str, expected_context: str, namespace: str) -> None:
    if not expected_context or actual_context != expected_context:
        raise ValueError("Kubernetes context does not match the protected environment")
    if namespace != NAMESPACE:
        raise ValueError(f"namespace must be {NAMESPACE}")


def validate_existing_release(
    status: dict[str, Any],
    values: dict[str, Any],
    manifest: bytes,
    *,
    allow_standard_replacement: bool,
    approved_revision: str,
    approved_identity: str,
) -> dict[str, str]:
    if status.get("name") != RELEASE or status.get("namespace") != NAMESPACE:
        raise ValueError("existing Helm release name or namespace mismatch")
    owner = values.get("deploymentOwner")
    mode = values.get("kserve", {}).get("deploymentMode")
    if owner not in OWNERS:
        raise ValueError("existing Helm release ownership is missing or unsupported")
    if mode != OWNERS[owner]:
        raise ValueError("existing Helm release owner and KServe mode disagree")
    revision = str(status.get("version", ""))
    identity = hashlib.sha256(manifest).hexdigest()
    if revision != approved_revision or identity != approved_identity:
        raise ValueError("existing Helm revision or immutable manifest identity was not approved")
    if owner == "module3-standard" and not allow_standard_replacement:
        raise ValueError("existing Module III Standard release requires separate replacement authorization")
    return {"release": RELEASE, "namespace": NAMESPACE, "owner": owner, "mode": mode, "revision": revision, "identity": identity}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--actual-context", required=True)
    parser.add_argument("--expected-context", required=True)
    parser.add_argument("--namespace", default=NAMESPACE)
    parser.add_argument("--status", type=Path)
    parser.add_argument("--values", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--allow-standard-replacement", action="store_true")
    parser.add_argument("--approved-revision", default="")
    parser.add_argument("--approved-identity", default="")
    args = parser.parse_args()
    validate_target(args.actual_context, args.expected_context, args.namespace)
    existing = (args.status, args.values, args.manifest)
    if any(existing) and not all(existing):
        raise ValueError("status, values and manifest must be supplied together")
    if not any(existing):
        print(json.dumps({"release": RELEASE, "namespace": NAMESPACE, "state": "new"}, sort_keys=True))
        return
    result = validate_existing_release(
        json.loads(args.status.read_text()),
        json.loads(args.values.read_text()),
        args.manifest.read_bytes(),
        allow_standard_replacement=args.allow_standard_replacement,
        approved_revision=args.approved_revision,
        approved_identity=args.approved_identity,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
