"""Tests for optional KServe and local-model client helpers."""

import asyncio
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
    assert payload["feature_names"] == list(model_client.FEATURE_NAMES)
    assert "instances" in payload
    assert len(payload["instances"][0]) == 6
    assert payload["instances"][0][4] == 0.8
    assert payload["instances"][0][5] == 0.2


def test_extract_prediction_numeric_class():
    assert _extract_prediction({"predictions": [2]}) == CognitiveLoadLevel.HIGH


@pytest.mark.parametrize(
    "payload",
    [
        {"predictions": [True]},
        {"predictions": [1.0]},
        {"predictions": []},
        {"predictions": ["LOW", "HIGH"]},
        {"predictions": [["MEDIUM"]]},
        {"predictions": [{"label": "LOW"}]},
        {"unexpected": []},
    ],
)
def test_extract_prediction_rejects_ambiguous_or_invalid_classes(payload):
    with pytest.raises(ValueError):
        _extract_prediction(payload)


def test_predict_with_kserve_disabled(monkeypatch):
    monkeypatch.delenv("KSERVE_PREDICT_URL", raising=False)
    with pytest.raises(RuntimeError, match="KSERVE_PREDICT_URL"):
        asyncio.run(predict_with_kserve(_request()))


def test_predict_with_kserve_success(monkeypatch):
    provenance = _kserve_environment(monkeypatch)
    async def request(method, url, **kwargs):
        return {"predictions": ["HIGH"], "provenance": provenance}

    monkeypatch.setattr(model_client, "_kserve_request", request)
    assert asyncio.run(predict_with_kserve(_request())) == CognitiveLoadLevel.HIGH


def test_predict_with_kserve_unsupported_payload_fails(monkeypatch):
    _kserve_environment(monkeypatch)

    async def request(method, url, **kwargs):
        return {"predictions": ["???"]}

    monkeypatch.setattr(model_client, "_kserve_request", request)
    with pytest.raises(ValueError, match="unsupported"):
        asyncio.run(predict_with_kserve(_request()))


def test_predict_with_kserve_network_failure_fails(monkeypatch):
    _kserve_environment(monkeypatch)

    async def _raise(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr(model_client, "_kserve_request", _raise)
    with pytest.raises(ConnectionError, match="boom"):
        asyncio.run(predict_with_kserve(_request()))


def test_kserve_metadata_and_prediction_reject_mismatch_and_redirect(monkeypatch):
    provenance = _kserve_environment(monkeypatch)
    async def request(method, url, **kwargs):
        return provenance

    monkeypatch.setattr(model_client, "_kserve_request", request)
    assert asyncio.run(model_client.verified_kserve_provenance())["model_version"] == "7"

    provenance["model_version"] = "8"
    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(model_client.verified_kserve_provenance())


def test_kserve_rejects_untrusted_origin(monkeypatch):
    _kserve_environment(monkeypatch)
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://attacker.invalid/v1/models/classifier:predict")
    with pytest.raises(RuntimeError, match="trusted KServe origin"):
        asyncio.run(predict_with_kserve(_request()))


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "31", "not-a-number"])
def test_kserve_timeout_configuration_is_bounded(monkeypatch, value):
    monkeypatch.setenv("KSERVE_TIMEOUT_SECONDS", value)
    with pytest.raises(RuntimeError, match="KSERVE_TIMEOUT_SECONDS"):
        model_client._kserve_timeout()


def test_kserve_timeout_extension_requires_educational_app_environment(monkeypatch):
    monkeypatch.setenv("KSERVE_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="at most 30"):
        model_client._kserve_timeout()

    monkeypatch.setenv("APP_ENV", "educational_demo")
    assert model_client._kserve_timeout() == 120

    monkeypatch.setenv("KSERVE_TIMEOUT_SECONDS", "181")
    with pytest.raises(RuntimeError, match="at most 180"):
        model_client._kserve_timeout()


def test_kserve_prediction_requires_matching_provenance(monkeypatch):
    provenance = _kserve_environment(monkeypatch)
    provenance["model_version"] = "8"

    async def request(method, url, **kwargs):
        return {"predictions": ["LOW"], "provenance": provenance}

    monkeypatch.setattr(model_client, "_kserve_request", request)
    with pytest.raises(ValueError, match="does not match"):
        asyncio.run(predict_with_kserve(_request()))


@pytest.mark.parametrize(
    "name,value",
    [
        ("MODEL_NAME", "CHANGE_ME"),
        ("MODEL_VERSION", "0"),
        ("MODEL_ARTIFACT_SHA256", "0" * 64),
        ("MODEL_SHA256", "0" * 64),
        ("MODEL_DATASET_SHA256", "0" * 64),
    ],
)
def test_kserve_expected_provenance_rejects_placeholders(monkeypatch, name, value):
    _kserve_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="placeholder or invalid"):
        model_client._expected_kserve_provenance()


def test_engineering_provenance_is_explicit_and_prohibited_in_production(monkeypatch):
    provenance = _kserve_environment(monkeypatch)
    monkeypatch.setenv("ALLOW_SYNTHETIC_ENGINEERING_MODEL", "true")
    monkeypatch.setenv("MODEL_VERSION", "engineering-2b")
    expected = model_client._expected_kserve_provenance()
    assert expected["approval_status"] == "engineering_fixture"
    assert expected["validation_scope"] == "synthetic_proxy_engineering_only"

    provenance.update(expected)
    assert model_client._validate_kserve_provenance(provenance) == provenance
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="prohibited"):
        model_client._expected_kserve_provenance()


def test_kserve_http_client_disables_redirects_and_maps_failures(monkeypatch):
    import httpx

    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            raise httpx.ReadTimeout("late")

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    with pytest.raises(TimeoutError, match="timed out"):
        asyncio.run(model_client._kserve_request("GET", "http://internal/ready"))
    assert captured["follow_redirects"] is False
    assert captured["trust_env"] is False


def test_kserve_http_client_rejects_redirect(monkeypatch):
    import httpx

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            return httpx.Response(302, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    with pytest.raises(ValueError, match="redirect"):
        asyncio.run(model_client._kserve_request("GET", "http://internal/ready"))


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
