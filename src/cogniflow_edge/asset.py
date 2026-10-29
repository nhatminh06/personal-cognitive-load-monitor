"""Pinned MediaPipe model identity; normal operation never downloads assets."""

from __future__ import annotations

import hashlib
from pathlib import Path

ASSET_NAME = "face_landmarker_float16_v1"
ASSET_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
ASSET_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)


def verify_asset(path: str | Path) -> Path:
    asset = Path(path)
    if not asset.is_file():
        raise FileNotFoundError(f"Reviewed Face Landmarker asset is missing: {asset}")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    if digest != ASSET_SHA256:
        raise ValueError(f"Unreviewed Face Landmarker asset (SHA-256 {digest})")
    return asset
