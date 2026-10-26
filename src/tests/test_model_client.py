"""Tests for optional KServe and local-model client helpers."""

import hashlib

import pytest

from preprocessing_api import model_client
from preprocessing_api.model_client import (
    _extract_prediction,
    kserve_payload,
    predict_with_kserve,
    predict_with_local_model,
)
from preprocessing_api.schemas import CognitiveLoadLevel, PredictionRequest


def _request() -> PredictionRequest:
    return PredictionRequest(
        focus_minutes=120,
        distraction_minutes=30,
        tasks_due=3,
        hours_to_deadline=24.0,
    )


@pytest.fixture(autouse=True)
def _reset_local_model_cache():
    model_client.reset_local_model_cache()
    yield
    model_client.reset_local_model_cache()


def test_kserve_payload_contains_engineered_features():
    payload = kserve_payload(_request())
    assert "instances" in payload
    assert len(payload["instances"][0]) == 6
    assert payload["instances"][0][4] == 0.8
    assert payload["instances"][0][5] == 0.2


def test_extract_prediction_numeric_class():
    assert _extract_prediction({"predictions": [2]}) == CognitiveLoadLevel.HIGH


def test_extract_prediction_nested_label():
    assert _extract_prediction({"predictions": [["MEDIUM"]]}) == CognitiveLoadLevel.MEDIUM


def test_extract_prediction_dict_label():
    assert _extract_prediction({"predictions": [{"label": "LOW"}]}) == CognitiveLoadLevel.LOW


def test_extract_prediction_unknown_payload_returns_none():
    assert _extract_prediction({"unexpected": []}) is None
    assert _extract_prediction({"predictions": ["UNKNOWN"]}) is None


def test_predict_with_kserve_disabled(monkeypatch):
    monkeypatch.delenv("KSERVE_PREDICT_URL", raising=False)
    with pytest.raises(RuntimeError, match="KSERVE_PREDICT_URL"):
        predict_with_kserve(_request())


def test_predict_with_kserve_success(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    class _FakeResponse:
        text = '{"predictions": [2]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"predictions": [2]}

    def _fake_post(url, json, timeout):
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)
    assert predict_with_kserve(_request()) == CognitiveLoadLevel.HIGH


def test_predict_with_kserve_unsupported_payload_fails(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    class _FakeResponse:
        text = '{"predictions": ["???"]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"predictions": ["???"]}

    monkeypatch.setattr("requests.post", lambda url, json, timeout: _FakeResponse())
    with pytest.raises(ValueError, match="unsupported"):
        predict_with_kserve(_request())


def test_predict_with_kserve_network_failure_fails(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr("requests.post", _raise)
    with pytest.raises(ConnectionError, match="KServe prediction failed"):
        predict_with_kserve(_request())


def test_predict_with_local_model_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "does-not-exist.joblib"))
    assert predict_with_local_model(_request()) is None


@pytest.mark.parametrize(
    "prediction,expected",
    [
        (0, CognitiveLoadLevel.LOW),
        (1, CognitiveLoadLevel.MEDIUM),
        (2, CognitiveLoadLevel.HIGH),
        ("LOW", CognitiveLoadLevel.LOW),
        ("MEDIUM", CognitiveLoadLevel.MEDIUM),
        ("HIGH", CognitiveLoadLevel.HIGH),
    ],
)
def test_predict_with_local_model_supported_classes(monkeypatch, tmp_path, prediction, expected):
    class _FakeModel:
        def predict(self, features):
            return [prediction]

    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"placeholder")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setattr("joblib.load", lambda path: _FakeModel())

    assert predict_with_local_model(_request()) == expected


@pytest.mark.parametrize("prediction", ["UNKNOWN", 3, 1.5, True])
def test_predict_with_local_model_rejects_unknown_classes(monkeypatch, tmp_path, prediction):
    class _FakeModel:
        def predict(self, features):
            return [prediction]

    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"placeholder")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setattr("joblib.load", lambda path: _FakeModel())

    assert predict_with_local_model(_request()) is None


def test_local_skops_model_uses_explicit_trusted_types(monkeypatch, tmp_path):
    model_path = tmp_path / "model.skops"
    model_path.write_bytes(b"trusted-skops")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setenv("MODEL_SHA256", hashlib.sha256(model_path.read_bytes()).hexdigest())
    calls = []
    fake_model = type("Model", (), {"predict": lambda self, _: ["LOW"]})()

    def load(path, *, trusted):
        calls.append((path, trusted))
        return fake_model

    monkeypatch.setattr("skops.io.load", load)
    assert predict_with_local_model(_request()) == CognitiveLoadLevel.LOW
    assert calls == [(model_path, ["sklearn.tree._tree.Tree"])]


def test_production_model_requires_matching_digest(monkeypatch, tmp_path):
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"trusted-model")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("MODEL_SHA256", raising=False)
    assert predict_with_local_model(_request()) is None

    model_client.reset_local_model_cache()
    monkeypatch.setenv("MODEL_SHA256", "0" * 64)
    assert predict_with_local_model(_request()) is None

    model_client.reset_local_model_cache()
    monkeypatch.setenv("MODEL_SHA256", hashlib.sha256(b"trusted-model").hexdigest())
    fake_model = type("Model", (), {"predict": lambda self, _: [1]})()
    monkeypatch.setattr("joblib.load", lambda path: fake_model)
    assert predict_with_local_model(_request()) == CognitiveLoadLevel.MEDIUM


def test_predict_with_local_model_prediction_failure_returns_none(monkeypatch, tmp_path):
    class _FakeModel:
        def predict(self, features):
            raise RuntimeError("bad input")

    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"placeholder")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setattr("joblib.load", lambda path: _FakeModel())

    assert predict_with_local_model(_request()) is None


def test_local_model_cache_reused_across_calls(monkeypatch, tmp_path):
    load_calls = []

    class _FakeModel:
        def predict(self, features):
            return [0]

    def _fake_load(path):
        load_calls.append(path)
        return _FakeModel()

    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"placeholder")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setattr("joblib.load", _fake_load)

    predict_with_local_model(_request())
    predict_with_local_model(_request())

    assert len(load_calls) == 1
