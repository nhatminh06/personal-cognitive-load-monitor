from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from cogniflow_kserve.predictor import CogniFlowPredictor
from scripts.generate_qualification_model import main as generate_qualification_model
from scripts.module1_qualification_model import qualification_environment


def configure(monkeypatch: pytest.MonkeyPatch, package: Path) -> dict[str, str]:
    environment = qualification_environment(package)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MODEL_PATH", str(package / "cognitive_load_model.skops"))
    monkeypatch.setenv("MODEL_PACKAGE_PATH", str(package / "model-package.json"))
    return environment


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    package = tmp_path / "model-package"
    monkeypatch.setattr(sys, "argv", ["generate_qualification_model.py", str(package)])
    generate_qualification_model()
    return package


def test_valid_synthetic_qualification_package_loads(
    monkeypatch: pytest.MonkeyPatch, package: Path,
) -> None:
    configure(monkeypatch, package)
    predictor = CogniFlowPredictor()
    assert predictor.load() is True
    assert predictor.provenance and predictor.provenance["model_name"] == "qualification-model"


def test_incorrect_model_sha_is_rejected(
    monkeypatch: pytest.MonkeyPatch, package: Path,
) -> None:
    environment = configure(monkeypatch, package)
    monkeypatch.setenv("MODEL_SHA256", "f" * 64)
    assert environment["MODEL_SHA256"] == hashlib.sha256(
        (package / "cognitive_load_model.skops").read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="deployment configuration"):
        CogniFlowPredictor().load()


@pytest.mark.parametrize(
    "field,value",
    [("model_name", "production-model"), ("registered_source", "models:/production")],
)
def test_incorrect_qualification_metadata_is_rejected(
    package: Path, field: str, value: str,
) -> None:
    manifest_path = package / "model-package.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="disposable qualification identity"):
        qualification_environment(package)


def test_production_environment_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, package: Path,
) -> None:
    production = {
        "MODEL_NAME": "production-model",
        "MODEL_VERSION": "42",
        "MODEL_SHA256": "a" * 64,
        "MODEL_ARTIFACT_SHA256": "b" * 64,
        "MODEL_DATASET_SHA256": "c" * 64,
        "MODEL_FEATURE_SCHEMA_VERSION": "1.0",
        "MODEL_PACKAGE_PATH": "/production/model-package.json",
    }
    for name, value in production.items():
        monkeypatch.setenv(name, value)
    qualification_environment(package)
    assert {name: os.environ[name] for name in production} == production
