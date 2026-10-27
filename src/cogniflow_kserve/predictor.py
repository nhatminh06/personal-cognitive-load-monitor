"""Verified model core used by the KServe ModelServer adapter."""

from __future__ import annotations

import hashlib
import math
import os
from numbers import Real
from pathlib import Path
from typing import Any

import skops.io

from preprocessing_api.model_client import (
    _SKOPS_TRUSTED_TYPES,
    _validated_class,
    validated_package_manifest,
)


class CogniFlowPredictor:
    """Load one approved package and serve strict six-feature V1 requests."""

    def __init__(self) -> None:
        self.ready = False
        self.model: Any = None
        self.provenance: dict[str, Any] | None = None

    def load(self) -> bool:
        model_path = Path(os.getenv("MODEL_PATH", "/app/models/cognitive_load_model.skops"))
        if not model_path.is_file() or model_path.suffix != ".skops":
            raise ValueError("approved skops model artifact is unavailable")
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        manifest = validated_package_manifest(model_path, digest)
        self.model = skops.io.load(model_path, trusted=_SKOPS_TRUSTED_TYPES)
        self.provenance = manifest
        self.ready = True
        return True

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.ready or self.model is None or self.provenance is None:
            raise RuntimeError("verified model is not ready")
        if set(payload) != {"instances"} or not isinstance(payload["instances"], list):
            raise ValueError("request must contain only an instances array")
        instances = payload["instances"]
        if not instances:
            raise ValueError("instances must not be empty")
        validated: list[list[float]] = []
        for row in instances:
            if not isinstance(row, list) or len(row) != 6:
                raise ValueError("each instance must contain six ordered features")
            if any(isinstance(value, bool) or not isinstance(value, Real) for value in row):
                raise ValueError("features must be numeric and must not be boolean")
            values = [float(value) for value in row]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("features must be finite")
            validated.append(values)
        predictions = [_validated_class(value).value for value in self.model.predict(validated)]
        if len(predictions) != len(validated):
            raise ValueError("model returned an unexpected prediction count")
        return {"predictions": predictions, "provenance": self.provenance}
