"""Tests for optional KServe and local-model client helpers."""

import hashlib
import json

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


def _kserve_environment(monkeypatch):
    origin = "http://classifier.cognitive-load-kserve.svc.cluster.local"
    provenance = {
        "contract_version": "1.0",
        "approval_status": "approved",
        "model_name": "classifier",
        "model_version": "7",
        "run_id": "run-1",
        "registered_source": "models:/immutable",
        "registered_artifact_sha256": "a" * 64,
        "packaged_model_sha256": "c" * 64,
        "dataset_sha256": "b" * 64,
        "feature_schema_version": "1.0",
        "feature_names": [
            "focus_minutes", "distraction_minutes", "tasks_due", "hours_to_deadline",
            "focus_ratio", "distraction_ratio",
        ],
        "label_provenance": "synthetic_proxy",
        "git_revision": "d" * 40,
        "approved_by": "owner",
        "approved_at": "2026-10-26T00:00:00+00:00",
    }
    values = {
        "KSERVE_ALLOWED_ORIGIN": origin,
        "KSERVE_PREDICT_URL": f"{origin}/v1/models/classifier:predict",
        "KSERVE_METADATA_URL": f"{origin}/v1/models/classifier/metadata",
        "MODEL_NAME": "classifier",
        "MODEL_VERSION": "7",
        "MODEL_ARTIFACT_SHA256": "a" * 64,
        "MODEL_SHA256": "c" * 64,
        "MODEL_DATASET_SHA256": "b" * 64,
        "MODEL_FEATURE_SCHEMA_VERSION": "1.0",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return provenance


def _skops_package(monkeypatch, tmp_path):
    model_path = tmp_path / "cognitive_load_model.skops"
    model_path.write_bytes(b"trusted-skops")
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
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
    values = {
        "MODEL_PATH": str(model_path),
        "MODEL_PACKAGE_PATH": str(manifest_path),
        "MODEL_SHA256": digest,
        "MODEL_NAME": "classifier",
        "MODEL_VERSION": "7",
        "MODEL_ARTIFACT_SHA256": "a" * 64,
        "MODEL_DATASET_SHA256": "b" * 64,
        "MODEL_FEATURE_SCHEMA_VERSION": "1.0",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return model_path, manifest_path, manifest


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
    provenance = _kserve_environment(monkeypatch)

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"predictions": ["HIGH"], "provenance": provenance}

    def _fake_post(url, json, timeout, allow_redirects):
        assert allow_redirects is False
        return _FakeResponse()

    monkeypatch.setattr("requests.post", _fake_post)
    assert predict_with_kserve(_request()) == CognitiveLoadLevel.HIGH


def test_predict_with_kserve_unsupported_payload_fails(monkeypatch):
    _kserve_environment(monkeypatch)

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"predictions": ["???"]}

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: _FakeResponse())
    with pytest.raises(ValueError, match="unsupported"):
        predict_with_kserve(_request())


def test_predict_with_kserve_network_failure_fails(monkeypatch):
    _kserve_environment(monkeypatch)

    def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr("requests.post", _raise)
    with pytest.raises(ConnectionError, match="KServe prediction failed"):
        predict_with_kserve(_request())


def test_kserve_metadata_and_prediction_reject_mismatch_and_redirect(monkeypatch):
    provenance = _kserve_environment(monkeypatch)

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return provenance

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _Response())
    assert model_client.verified_kserve_provenance()["model_version"] == "7"

    provenance["model_version"] = "8"
    with pytest.raises(ValueError, match="does not match"):
        model_client.verified_kserve_provenance()

    provenance["model_version"] = "7"
    _Response.status_code = 302
    with pytest.raises(ValueError, match="redirect"):
        model_client.verified_kserve_provenance()


def test_kserve_rejects_untrusted_origin(monkeypatch):
    _kserve_environment(monkeypatch)
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://attacker.invalid/v1/models/classifier:predict")
    with pytest.raises(RuntimeError, match="trusted KServe origin"):
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
    model_path, _, _ = _skops_package(monkeypatch, tmp_path)
    calls = []
    fake_model = type("Model", (), {"predict": lambda self, _: ["LOW"]})()

    def load(path, *, trusted):
        calls.append((path, trusted))
        return fake_model

    monkeypatch.setattr("skops.io.load", load)
    assert predict_with_local_model(_request()) == CognitiveLoadLevel.LOW
    assert calls == [(model_path, ["sklearn.tree._tree.Tree"])]


def test_genuine_skops_round_trip_uses_packaged_contract(monkeypatch, tmp_path):
    import skops.io
    from sklearn.ensemble import RandomForestClassifier

    model_path, manifest_path, manifest = _skops_package(monkeypatch, tmp_path)
    model = RandomForestClassifier(n_estimators=2, random_state=42).fit(
        [[150, 10, 0, 96, 0.9375, 0.0625], [30, 120, 8, 4, 0.2, 0.8]],
        ["LOW", "HIGH"],
    )
    skops.io.dump(model, model_path)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    manifest["packaged_model_sha256"] = digest
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setenv("MODEL_SHA256", digest)

    assert predict_with_local_model(_request()) in {
        CognitiveLoadLevel.LOW,
        CognitiveLoadLevel.HIGH,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_name", "tampered"),
        ("approval_status", "candidate"),
        ("model_version", "8"),
        ("registered_artifact_sha256", "d" * 64),
        ("dataset_sha256", "d" * 64),
        ("feature_schema_version", "2.0"),
        ("feature_names", ["tasks_due"]),
        ("packaged_model_sha256", "d" * 64),
    ],
)
def test_skops_manifest_tampering_fails_before_deserialization(
    monkeypatch, tmp_path, field, value
):
    _, manifest_path, manifest = _skops_package(monkeypatch, tmp_path)
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        "skops.io.load", lambda *args, **kwargs: pytest.fail("must fail before deserialization")
    )
    assert predict_with_local_model(_request()) is None


@pytest.mark.parametrize(
    "name,value",
    [
        ("MODEL_NAME", "other"),
        ("MODEL_VERSION", "8"),
        ("MODEL_ARTIFACT_SHA256", "d" * 64),
        ("MODEL_DATASET_SHA256", "d" * 64),
        ("MODEL_FEATURE_SCHEMA_VERSION", "2.0"),
    ],
)
def test_skops_deployment_configuration_mismatch_fails_closed(
    monkeypatch, tmp_path, name, value
):
    _skops_package(monkeypatch, tmp_path)
    monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        "skops.io.load", lambda *args, **kwargs: pytest.fail("must fail before deserialization")
    )
    assert predict_with_local_model(_request()) is None


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
