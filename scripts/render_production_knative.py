"""Render local Knative manifests with immutable production image references."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


IMAGE_RE = re.compile(
    r"^[a-z0-9-]+-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/"
    r"cogniflow-images/[a-z0-9-]+@sha256:[a-f0-9]{64}$"
)
FILES = (
    "namespace.yaml", "networkpolicy.yaml", "broker.yaml", "trigger.yaml",
    "anomaly-trigger.yaml", "consumer.yaml", "dead-letter.yaml", "anomaly.yaml",
)
IMAGES = {
    "cogniflow-event-consumer:dev": "event_consumer",
    "cogniflow-anomaly-detector:dev": "anomaly_detector",
}


def render(
    source: Path, replacements: dict[str, str], durable_channel_configmap: str
) -> str:
    for image in replacements.values():
        if not IMAGE_RE.fullmatch(image):
            raise ValueError(f"production image must be an Artifact Registry digest: {image}")

    documents: list[dict[str, object]] = []
    replaced: set[str] = set()
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", durable_channel_configmap):
        raise ValueError("durable channel ConfigMap must be a DNS label")
    if durable_channel_configmap == "config-br-default-channel":
        raise ValueError("production Broker must not use the default in-memory channel config")
    for filename in FILES:
        for document in yaml.safe_load_all((source / filename).read_text()):
            if not document:
                continue
            if document.get("kind") == "Broker":
                document["spec"]["config"]["name"] = durable_channel_configmap
            containers = (
                document.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers", [])
            )
            for container in containers:
                key = IMAGES.get(container.get("image"))
                if key:
                    container["image"] = replacements[key]
                    container["imagePullPolicy"] = "IfNotPresent"
                    replaced.add(key)
                image = container.get("image", "")
                if not IMAGE_RE.fullmatch(image):
                    raise ValueError(f"mutable or development image remains in {filename}: {image}")
            documents.append(document)
    if replaced != set(replacements):
        raise ValueError("not every required production image replaced a development image")
    return yaml.safe_dump_all(documents, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("deploy/knative"))
    parser.add_argument("--event-consumer", required=True)
    parser.add_argument("--anomaly-detector", required=True)
    parser.add_argument("--durable-channel-configmap", required=True)
    args = parser.parse_args()
    try:
        sys.stdout.write(
            render(
                args.source,
                {
                    "event_consumer": args.event_consumer,
                    "anomaly_detector": args.anomaly_detector,
                },
                args.durable_channel_configmap,
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
