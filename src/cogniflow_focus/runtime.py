"""Fail-closed local runtime for strict focus-model packages."""

from __future__ import annotations

import importlib.metadata
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import skops.io
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from preprocessing_api.security import is_production

from .package import (
    FocusModelManifest,
    enforce_local_fixture_governance,
    validate_focus_package,
)


def _major_minor(value: str) -> tuple[str, str]:
    parts = value.split(".")
    if len(parts) < 2 or not all(part.isdigit() for part in parts[:2]):
        raise ValueError("runtime version is malformed")
    return parts[0], parts[1]


class FocusModelRuntime:
    def __init__(self, package_dir: Path, *, allow_synthetic_fixture: bool = False) -> None:
        self.package_dir = package_dir
        self.allow_synthetic_fixture = allow_synthetic_fixture
        self.manifest: FocusModelManifest | None = None
        self.model: Pipeline | None = None

    @property
    def ready(self) -> bool:
        return self.model is not None and self.manifest is not None

    def load(self) -> None:
        manifest, model_path = validate_focus_package(self.package_dir)
        enforce_local_fixture_governance(manifest)
        if is_production():
            raise ValueError("synthetic focus models are prohibited in production")
        if not self.allow_synthetic_fixture:
            raise ValueError("synthetic focus model requires explicit local test mode")
        installed = {
            "python": ".".join(map(str, sys.version_info[:3])),
            "numpy": importlib.metadata.version("numpy"),
            "pandas": importlib.metadata.version("pandas"),
            "scikit-learn": importlib.metadata.version("scikit-learn"),
            "skops": importlib.metadata.version("skops"),
        }
        for name, current in installed.items():
            recorded = manifest.runtime_versions.get(name)
            if recorded is None or _major_minor(recorded) != _major_minor(current):
                raise ValueError(f"unsupported {name} runtime version")
        loaded = skops.io.load(model_path, trusted=list(manifest.skops_trusted_types))
        self._validate_pipeline(loaded, manifest)
        probe = {name: 0.0 for name in manifest.feature_names}
        for name in manifest.feature_names:
            if manifest.feature_contract[name]["nullable"]:
                probe[name] = float("nan")
        prediction = loaded.predict(pd.DataFrame([probe], columns=manifest.feature_names))
        if len(prediction) != 1 or not math.isfinite(float(prediction[0])):
            raise ValueError("focus model returned an invalid validation prediction")
        self.model, self.manifest = loaded, manifest

    @staticmethod
    def _validate_pipeline(model: Any, manifest: FocusModelManifest) -> None:
        if type(model) is not Pipeline or tuple(model.feature_names_in_) != manifest.feature_names:
            raise ValueError("focus model pipeline or feature ordering is incompatible")
        allowed_steps: dict[str, tuple[tuple[str, type[Any]], ...]] = {
            "dummy_median": (("imputer", SimpleImputer), ("regressor", DummyRegressor)),
            "ridge": (("imputer", SimpleImputer), ("scaler", StandardScaler), ("regressor", Ridge)),
            "random_forest": (
                ("imputer", SimpleImputer), ("regressor", RandomForestRegressor),
            ),
        }
        expected = allowed_steps[manifest.model_family]
        if len(model.steps) != len(expected) or any(
            name != expected_name or type(step) is not expected_type
            for (name, step), (expected_name, expected_type) in zip(model.steps, expected)
        ):
            raise ValueError("focus model contains an incompatible estimator or preprocessor")
        if model.named_steps["imputer"].strategy != "median":
            raise ValueError("focus model missing-value policy is incompatible")
        regressor = model.named_steps["regressor"]
        actual_config = regressor.get_params(deep=False)
        if any(actual_config.get(name) != value for name, value in manifest.model_configuration.items()):
            raise ValueError("focus model configuration does not match its manifest")

    def predict(self, features: dict[str, int | float | None]) -> float:
        if not self.ready or self.model is None or self.manifest is None:
            raise RuntimeError("focus model is not ready")
        if tuple(features) != self.manifest.feature_names:
            raise ValueError("focus feature ordering does not match the package")
        frame = pd.DataFrame([features], columns=self.manifest.feature_names)
        prediction = self.model.predict(frame)
        if len(prediction) != 1 or not math.isfinite(float(prediction[0])):
            raise ValueError("focus model returned a nonfinite or invalid prediction")
        return min(7.0, max(1.0, float(prediction[0])))
