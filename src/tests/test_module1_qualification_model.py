from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from cogniflow_kserve.predictor import CogniFlowPredictor
from scripts.module1_qualification_model import qualification_environment

ROOT = Path(__file__).parents[2]
PACKAGE = ROOT / "build/model-package"


def configure(monkeypatch: pytest.MonkeyPatch, package: Path) -> dict[str, str]:
    environment = qualification_environment(package)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("MODEL_PATH", str(package / "cognitive_load_model.skops"))
    monkeypatch.setenv("MODEL_PACKAGE_PATH", str(package / "model-package.json"))
    return environment


def copied_package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    package.mkdir()
    for name in ("cognitive_load_model.skops", "model-package.json"):
        (package / name).write_bytes((PACKAGE / name).read_bytes())
    return package


def test_valid_synthetic_qualification_package_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch, PACKAGE)
    predictor = CogniFlowPredictor()
    assert predictor.load() is True
    assert predictor.provenance and predictor.provenance["model_name"] == "qualification-model"


def test_incorrect_model_sha_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = configure(monkeypatch, PACKAGE)
    monkeypatch.setenv("MODEL_SHA256", "f" * 64)
    assert environment["MODEL_SHA256"] == hashlib.sha256(
        (PACKAGE / "cognitive_load_model.skops").read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="deployment configuration"):
        CogniFlowPredictor().load()


@pytest.mark.parametrize(
    "field,value",
    [("model_name", "production-model"), ("registered_source", "models:/production")],
)
def test_incorrect_qualification_metadata_is_rejected(
    tmp_path: Path, field: str, value: str,
) -> None:
    package = copied_package(tmp_path)
    manifest_path = package / "model-package.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="disposable qualification identity"):
        qualification_environment(package)


def test_production_environment_is_not_overwritten(monkeypatch: pytest.MonkeyPatch) -> None:
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
    qualification_environment(PACKAGE)
    assert {name: os.environ[name] for name in production} == production
