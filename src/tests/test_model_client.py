"""Tests for optional KServe model client helpers."""

from preprocessing_api.model_client import _extract_prediction, kserve_payload, predict_with_kserve
from preprocessing_api.schemas import CognitiveLoadLevel, PredictionRequest


def _request() -> PredictionRequest:
    return PredictionRequest(
        focus_minutes=120,
        distraction_minutes=30,
        tasks_due=3,
        hours_to_deadline=24.0,
    )


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
