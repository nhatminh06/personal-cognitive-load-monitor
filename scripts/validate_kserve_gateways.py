"""Validate that KServe's configured Istio gateways exist in a captured inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_gateway_refs(
    config_map: dict[str, Any],
    gateway_list: dict[str, Any],
    *,
    expected_ingress: str,
    expected_local: str,
) -> None:
    try:
        ingress = json.loads(config_map["data"]["ingress"])
        configured = {ingress["ingressGateway"], ingress["localGateway"]}
        available = {
            f"{item['metadata']['namespace']}/{item['metadata']['name']}"
            for item in gateway_list["items"]
            if item.get("kind") == "Gateway"
        }
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("KServe gateway inventory is malformed") from exc

    expected = {expected_ingress, expected_local}
    if configured != expected:
        raise ValueError(
            f"KServe gateways {sorted(configured)} do not match expected {sorted(expected)}"
        )
    missing = configured - available
    if missing:
        raise ValueError(f"configured KServe Gateway does not exist: {sorted(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-map", type=Path, required=True)
    parser.add_argument("--gateways", type=Path, required=True)
    parser.add_argument("--expected-ingress", required=True)
    parser.add_argument("--expected-local", required=True)
    args = parser.parse_args()
    validate_gateway_refs(
        json.loads(args.config_map.read_text()),
        json.loads(args.gateways.read_text()),
        expected_ingress=args.expected_ingress,
        expected_local=args.expected_local,
    )


if __name__ == "__main__":
    main()
