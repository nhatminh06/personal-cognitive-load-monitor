"""Tests for optional KServe and local-model client helpers."""

import pytest

from preprocessing_api import model_client
from preprocessing_api.model_client import (
    _extract_prediction,
    kserve_configured,
    kserve_payload,
    kserve_reachable,
    local_model_available,
    predict_with_kserve,
    predict_with_local_model,
    read_model_manifest,
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
    assert predict_with_kserve(_request()) is None


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


def test_predict_with_kserve_unsupported_payload_returns_none(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    class _FakeResponse:
        text = '{"predictions": ["???"]}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"predictions": ["???"]}

    monkeypatch.setattr("requests.post", lambda url, json, timeout: _FakeResponse())
    assert predict_with_kserve(_request()) is None


def test_predict_with_kserve_network_failure_returns_none(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr("requests.post", _raise)
    assert predict_with_kserve(_request()) is None


def test_predict_with_local_model_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "does-not-exist.joblib"))
    assert predict_with_local_model(_request()) is None


def test_predict_with_local_model_success(monkeypatch, tmp_path):
    class _FakeModel:
        def predict(self, features):
            return [1]

    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"placeholder")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setattr("joblib.load", lambda path: _FakeModel())

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


def test_local_model_available_true_when_model_loads(monkeypatch, tmp_path):
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"placeholder")
    monkeypatch.setenv("MODEL_PATH", str(model_path))
    monkeypatch.setattr("joblib.load", lambda path: object())
    assert local_model_available() is True


def test_local_model_available_false_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.joblib"))
    assert local_model_available() is False


def test_kserve_configured_true_when_url_set(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/predict")
    assert kserve_configured() is True


def test_kserve_configured_false_when_unset(monkeypatch):
    monkeypatch.delenv("KSERVE_PREDICT_URL", raising=False)
    assert kserve_configured() is False


def test_kserve_reachable_false_when_unconfigured(monkeypatch):
    monkeypatch.delenv("KSERVE_PREDICT_URL", raising=False)
    assert kserve_reachable() is False


def test_kserve_reachable_true_on_successful_get(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    class _FakeResponse:
        status_code = 200

    monkeypatch.setattr("requests.get", lambda url, timeout: _FakeResponse())
    assert kserve_reachable() is True


def test_kserve_reachable_false_on_server_error(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    class _FakeResponse:
        status_code = 503

    monkeypatch.setattr("requests.get", lambda url, timeout: _FakeResponse())
    assert kserve_reachable() is False


def test_kserve_reachable_false_on_connection_error(monkeypatch):
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://kserve.example/v1/models/x:predict")

    def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr("requests.get", _raise)
    assert kserve_reachable() is False


def test_read_model_manifest_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "model.joblib"))
    assert read_model_manifest() is None


def test_read_model_manifest_reads_sidecar_json(monkeypatch, tmp_path):
    model_path = tmp_path / "model.joblib"
    manifest_path = tmp_path / "model.joblib.manifest.json"
    manifest_path.write_text('{"model_uri": "models:/cognitive-load-classifier/1", "source": "mlflow"}')
    monkeypatch.setenv("MODEL_PATH", str(model_path))

    manifest = read_model_manifest()
    assert manifest["model_uri"] == "models:/cognitive-load-classifier/1"
    assert manifest["source"] == "mlflow"


def test_read_model_manifest_corrupt_json_returns_none(monkeypatch, tmp_path):
    model_path = tmp_path / "model.joblib"
    manifest_path = tmp_path / "model.joblib.manifest.json"
    manifest_path.write_text("not valid json {")
    monkeypatch.setenv("MODEL_PATH", str(model_path))

    assert read_model_manifest() is None
