"""Pin exact qualification images and omit the disabled kernel-cache agent."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml


IMAGE_DIGESTS = {
    "docker.io/istio/install-cni:1.31.3": "sha256:115d9d77a6f70da7ea84f997964e871bf4c9b0f235e56aed30c773ffd7154b06",
    "docker.io/istio/pilot:1.31.3": "sha256:1a349da3d48a59f2663256b50284de6ff84776db5ea9f42d426f752b34b44e62",
    "docker.io/istio/proxyv2:1.31.3": "sha256:be401d180020fd4dba0d106135e1af1fb8f3796868c581068081a18c94c2534c",
    "kserve/kserve-controller:v0.21.0": "sha256:878cb1a071a378b25da91c2d74c03d88e288dbbcdaf7cb87c776dcc849fcdf5f",
    "kserve/kserve-localmodel-controller:v0.21.0": "sha256:ef525ebc445e1fe6108c4c013d819620e5d80e1450539fb54ff65ace0c959a83",
    "kserve/llmisvc-controller:v0.21.0": "sha256:e3d71368f622e8c57a088de15e23c28f981c6c51b4b028cb1b1081f0c472adf1",
    "quay.io/brancz/kube-rbac-proxy:v0.18.0": "sha256:62eeb8a0aaa13a8d886de07e5805940cec079ffbaf1d74483e26ad4a84952dce",
    "quay.io/jetstack/cert-manager-cainjector:v1.21.2": "sha256:aa2bc58725d92a643f5069dde58abc93b65566ded8951348873ac9ee7efef66c",
    "quay.io/jetstack/cert-manager-controller:v1.21.2": "sha256:57bb397c639e0e94184ba67848e5dad04284f24645e521e764a0ee5f5002f286",
    "quay.io/jetstack/cert-manager-webhook:v1.21.2": "sha256:b929259301ee75270ab4651d5e6bd4ba7b6624b1ce48ba767d064295a9312101",
}
FILES = (
    "kubeflow-namespace.yaml", "cert-manager.yaml", "istio-crds.yaml", "istio-namespace.yaml", "istio.yaml",
    "knative-serving.yaml", "cluster-local-gateway.yaml", "kserve.yaml",
)
OMITTED = ("DaemonSet", "kserve", "kserve-kernelcachenode-agent")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(mode=0o700)
    replacements = dict.fromkeys(IMAGE_DIGESTS, 0)
    excluded: list[dict[str, str]] = []
    manifests: dict[str, dict[str, str]] = {}
    for name in FILES:
        source = input_dir / name
        raw = source.read_bytes()
        parts = re.split(rb"(?m)^---[ \t]*\r?\n", raw)
        kept = []
        for part in parts:
            if OMITTED[2].encode() in part:
                document = yaml.safe_load(part)
                metadata = document.get("metadata", {}) if isinstance(document, dict) else {}
                identity = (document.get("kind"), metadata.get("namespace", "default"), metadata.get("name"))
                if identity == OMITTED:
                    excluded.append({"kind": identity[0], "namespace": identity[1], "name": identity[2]})
                    continue
            if part.strip():
                kept.append(part.rstrip() + b"\n")
        rendered = b"---\n".join(kept)
        for image, digest in IMAGE_DIGESTS.items():
            count = rendered.count(image.encode())
            replacements[image] += count
            rendered = rendered.replace(image.encode(), f"{image.rsplit(':', 1)[0]}@{digest}".encode())
        target = output_dir / name
        target.write_bytes(rendered)
        manifests[name] = {"source_sha256": sha256(raw), "applied_sha256": sha256(rendered)}
    missing = sorted(image for image, count in replacements.items() if count == 0)
    if missing or len(excluded) != 1:
        raise ValueError(f"qualification manifest preparation mismatch: missing={missing}, excluded={excluded}")
    return {"manifests": manifests, "image_replacements": replacements, "excluded_resources": excluded}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    args.evidence.write_text(json.dumps(prepare(args.input_dir, args.output_dir), indent=2) + "\n")


if __name__ == "__main__":
    main()
