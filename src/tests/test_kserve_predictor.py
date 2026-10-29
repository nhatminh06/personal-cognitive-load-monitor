"""Security and protocol tests for the custom KServe predictor core."""

import hashlib
import json

import pytest
from kserve.errors import InvalidInput

from cogniflow_kserve.predictor import CogniFlowPredictor
from cogniflow_kserve.server import CogniFlowModel
from preprocessing_api.features import FEATURE_NAMES


def _payload(*rows):
    return {"feature_names": list(FEATURE_NAMES), "instances": list(rows)}


def _fake_model(predictions):
    return type(
        "Model",
        (),
        {
            "n_features_in_": 6,
            "feature_names_in_": list(FEATURE_NAMES),
            "classes_": ["HIGH", "LOW", "MEDIUM"],
            "predict": lambda self, rows: predictions,
        },
    )()


def _package(monkeypatch, tmp_path):
    model = tmp_path / "cognitive_load_model.skops"
    model.write_bytes(b"verified-skops")
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    manifest = {
        "contract_version": "1.0",
        "approval_status": "approved",
        "model_name": "classifier",
        "model_version": "7",
        "run_id": "run-1",
        "registered_source": "models:/immutable",
        "registered_artifact_sha256": "a" * 64,
        "packaged_model_sha256": digest,
        "dataset_sha256": "b" * 64,
        "feature_schema_version": "1.0",
        "feature_names": [
            "focus_minutes", "distraction_minutes", "tasks_due", "hours_to_deadline",
            "focus_ratio", "distraction_ratio",
        ],
        "label_provenance": "synthetic_proxy",
        "git_revision": "c" * 40,
        "approved_by": "owner",
        "approved_at": "2026-10-26T00:00:00+00:00",
    }
    manifest_path = tmp_path / "model-package.json"
    manifest_path.write_text(json.dumps(manifest))
    env = {
        "MODEL_PATH": str(model),
        "MODEL_PACKAGE_PATH": str(manifest_path),
        "MODEL_SHA256": digest,
        "MODEL_NAME": "classifier",
        "MODEL_VERSION": "7",
        "MODEL_ARTIFACT_SHA256": "a" * 64,
        "MODEL_DATASET_SHA256": "b" * 64,
        "MODEL_FEATURE_SCHEMA_VERSION": "1.0",
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return model, manifest_path, manifest


def test_predictor_loads_verified_package_and_predicts(monkeypatch, tmp_path):
    model_path, _, manifest = _package(monkeypatch, tmp_path)
    fake = _fake_model(["LOW", 2])
    monkeypatch.setattr("skops.io.load", lambda path, *, trusted: fake)
    predictor = CogniFlowPredictor()

    assert predictor.load() is True
    result = predictor.predict(_payload([1, 0, 0, 24, 1, 0], [2, 2, 1, 8, .5, .5]))
    assert result == {"predictions": ["LOW", "HIGH"], "provenance": manifest}
    assert predictor.ready is True
    assert model_path.is_file()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        _payload(),
        _payload([1, 2]),
        _payload([True, 0, 0, 1, 1, 0]),
        _payload([float("inf"), 0, 0, 1, 1, 0]),
        {"feature_names": ["wrong"], "instances": [[1, 0, 0, 24, 1, 0]]},
        _payload([-1, 0, 0, 24, 0, 0]),
        _payload([1, 1, 0, 24, 1, 0]),
    ],
)
def test_predictor_rejects_invalid_inputs(monkeypatch, tmp_path, payload):
    _package(monkeypatch, tmp_path)
    monkeypatch.setattr("skops.io.load", lambda *args, **kwargs: _fake_model(["LOW"]))
    predictor = CogniFlowPredictor()
    predictor.load()
    with pytest.raises(ValueError):
        predictor.predict(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("approval_status", "candidate"),
        ("model_name", "other"),
        ("model_version", "8"),
        ("registered_artifact_sha256", "d" * 64),
        ("packaged_model_sha256", "d" * 64),
        ("feature_schema_version", "2.0"),
        ("feature_names", ["wrong"]),
    ],
)
def test_predictor_rejects_manifest_before_deserialization(
    monkeypatch, tmp_path, field, value
):
    _, manifest_path, manifest = _package(monkeypatch, tmp_path)
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        "skops.io.load", lambda *args, **kwargs: pytest.fail("must fail before load")
    )
    with pytest.raises(ValueError):
        CogniFlowPredictor().load()


def test_predictor_rejects_missing_model_and_unknown_class(monkeypatch, tmp_path):
    model, _, _ = _package(monkeypatch, tmp_path)
    model.unlink()
    with pytest.raises(ValueError, match="unavailable"):
        CogniFlowPredictor().load()

    _package(monkeypatch, tmp_path)
    fake = _fake_model([1.5])
    monkeypatch.setattr("skops.io.load", lambda *args, **kwargs: fake)
    predictor = CogniFlowPredictor()
    predictor.load()
    with pytest.raises(ValueError, match="unsupported"):
        predictor.predict(_payload([1, 0, 0, 24, 1, 0]))


def test_predictor_rejects_inference_before_load():
    with pytest.raises(RuntimeError, match="not ready"):
        CogniFlowPredictor().predict(_payload([1, 0, 0, 24, 1, 0]))


def test_failed_reload_clears_readiness(monkeypatch, tmp_path):
    model, _, _ = _package(monkeypatch, tmp_path)
    monkeypatch.setattr("skops.io.load", lambda *args, **kwargs: _fake_model(["LOW"]))
    predictor = CogniFlowPredictor()
    predictor.load()
    assert predictor.ready is True

    model.unlink()
    with pytest.raises(ValueError, match="unavailable"):
        predictor.load()
    assert predictor.ready is False
    assert predictor.model is None
    assert predictor.provenance is None


def test_model_adapter_maps_invalid_client_input(monkeypatch):
    predictor = CogniFlowPredictor()
    predictor.ready = True
    predictor.model = _fake_model(["LOW"])
    predictor.provenance = {"model_name": "classifier"}
    model = CogniFlowModel("classifier", predictor=predictor)
    with pytest.raises(InvalidInput, match="exact feature names"):
        model.predict({"instances": [[1, 0, 0, 24, 1, 0]]})
