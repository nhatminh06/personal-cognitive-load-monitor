"""Verified model core used by the KServe ModelServer adapter."""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Callable
from numbers import Real
from pathlib import Path
from typing import Any

import skops.io
import pandas as pd

from preprocessing_api.model_client import (
    _SKOPS_TRUSTED_TYPES,
    _validated_class,
    validated_package_manifest,
)
from preprocessing_api.features import FEATURE_NAMES, feature_vector
from preprocessing_api.schemas import PredictionRequest


class CogniFlowPredictor:
    """Load one approved package and serve strict six-feature V1 requests."""

    def __init__(
        self,
        manifest_validator: Callable[[Path, str], dict[str, Any]] = validated_package_manifest,
    ) -> None:
        self.ready = False
        self.model: Any = None
        self.provenance: dict[str, Any] | None = None
        self._manifest_validator = manifest_validator

    def load(self) -> bool:
        self.ready = False
        self.model = None
        self.provenance = None
        model_path = Path(os.getenv("MODEL_PATH", "/app/models/cognitive_load_model.skops"))
        if not model_path.is_file() or model_path.suffix != ".skops":
            raise ValueError("approved skops model artifact is unavailable")
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        manifest = self._manifest_validator(model_path, digest)
        model = skops.io.load(model_path, trusted=_SKOPS_TRUSTED_TYPES)
        if (
            getattr(model, "n_features_in_", None) != len(FEATURE_NAMES)
            or list(getattr(model, "feature_names_in_", [])) != list(FEATURE_NAMES)
            or set(getattr(model, "classes_", [])) != {"LOW", "MEDIUM", "HIGH"}
        ):
            raise ValueError("loaded model contract is incompatible")
        self.model = model
        self.provenance = manifest
        self.ready = True
        return True

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.ready or self.model is None or self.provenance is None:
            raise RuntimeError("verified model is not ready")
        if (
            set(payload) != {"feature_names", "instances"}
            or payload["feature_names"] != list(FEATURE_NAMES)
            or not isinstance(payload["instances"], list)
        ):
            raise ValueError("request must contain exact feature names and an instances array")
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
            try:
                request = PredictionRequest(
                    focus_minutes=values[0],
                    distraction_minutes=values[1],
                    tasks_due=values[2],
                    hours_to_deadline=values[3],
                )
            except ValueError as exc:
                raise ValueError("raw feature values violate the input contract") from exc
            canonical = feature_vector(request.model_dump())
            if any(
                not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)
                for actual, expected in zip(values, canonical, strict=True)
            ):
                raise ValueError("derived features do not match the canonical feature contract")
            validated.append(values)
        frame = pd.DataFrame(validated, columns=FEATURE_NAMES)
        predictions = [_validated_class(value).value for value in self.model.predict(frame)]
        if len(predictions) != len(validated):
            raise ValueError("model returned an unexpected prediction count")
        return {"predictions": predictions, "provenance": self.provenance}
