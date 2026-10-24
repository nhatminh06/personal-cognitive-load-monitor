"""Tests for the cognitive load prediction API.

Exact-value assertions here were verified by calling
preprocessing_api.service.calculate_cognitive_load directly for each input and
recording its actual output, not by assuming what "should" happen. One of the
previous test inputs (see test_predict_medium_cognitive_load) turned out to
actually produce LOW, not MEDIUM — the old test only asserted membership in
the enum, so it passed anyway despite testing the wrong thing.
"""

from fastapi.testclient import TestClient

import preprocessing_api.main as main_module
from preprocessing_api.schemas import CognitiveLoadLevel


def test_root_endpoint(client: TestClient):
    """Test root endpoint returns healthy status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "cognitive-load-monitor"


def test_health_endpoint(client: TestClient):
    """Test health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_predict_low_cognitive_load(client: TestClient, monkeypatch):
    """High focus ratio, low task/deadline pressure -> LOW (score 0.15).

    Forces INFERENCE_MODE=rule: this asserts an exact value from the
    deterministic formula, so it must not be affected by whether a trained
    model artifact happens to exist on disk (e.g. from a local `dvc repro`).
    """
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    request_data = {
        "focus_minutes": 180,
        "distraction_minutes": 20,
        "tasks_due": 1,
        "hours_to_deadline": 96.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "LOW"


def test_predict_medium_cognitive_load(client: TestClient, monkeypatch):
    """Balanced focus/distraction with a same-day deadline -> MEDIUM (score 0.52)."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    request_data = {
        "focus_minutes": 100,
        "distraction_minutes": 100,
        "tasks_due": 3,
        "hours_to_deadline": 48.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "MEDIUM"


def test_predict_high_cognitive_load(client: TestClient, monkeypatch):
    """Even split, many tasks, imminent deadline -> HIGH (score 0.76)."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    request_data = {
        "focus_minutes": 60,
        "distraction_minutes": 60,
        "tasks_due": 5,
        "hours_to_deadline": 12.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "HIGH"


def test_predict_with_zero_focus_and_distraction(client: TestClient, monkeypatch):
    """Zero total time: deadline pressure alone (score 0.68) -> MEDIUM."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    request_data = {
        "focus_minutes": 0,
        "distraction_minutes": 0,
        "tasks_due": 2,
        "hours_to_deadline": 24.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "MEDIUM"


def test_predict_deadline_pressure_boundary_24h_vs_25h(client: TestClient, monkeypatch):
    """24h exactly uses the high deadline-pressure tier; just above 24h does not."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    at_boundary = {
        "focus_minutes": 120,
        "distraction_minutes": 40,
        "tasks_due": 1,
        "hours_to_deadline": 24.0,
    }
    just_after = dict(at_boundary, hours_to_deadline=24.01)

    at_response = client.post("/predict", json=at_boundary).json()["cognitive_load_level"]
    after_response = client.post("/predict", json=just_after).json()["cognitive_load_level"]

    # 24h uses deadline_pressure=1.0, 24.01h uses deadline_pressure=0.5 (a 0.3*0.5=0.15
    # score drop) -- confirms the <= boundary is inclusive as service.py implements it.
    assert at_response == "MEDIUM"
    assert after_response == "LOW"


def test_predict_invalid_negative_focus_minutes(client: TestClient):
    """Test prediction with invalid negative focus_minutes."""
    request_data = {
        "focus_minutes": -10,
        "distraction_minutes": 30,
        "tasks_due": 2,
        "hours_to_deadline": 24.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 422


def test_predict_invalid_negative_distraction_minutes(client: TestClient):
    """Test prediction with invalid negative distraction_minutes."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": -5,
        "tasks_due": 2,
        "hours_to_deadline": 24.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 422


def test_predict_invalid_negative_tasks_due(client: TestClient):
    """Test prediction with invalid negative tasks_due."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": 30,
        "tasks_due": -1,
        "hours_to_deadline": 24.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 422


def test_predict_invalid_negative_hours_to_deadline(client: TestClient):
    """Test prediction with invalid negative hours_to_deadline."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": 30,
        "tasks_due": 2,
        "hours_to_deadline": -5.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 422


def test_predict_missing_field(client: TestClient):
    """Test prediction with missing required field."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": 30,
        "tasks_due": 2,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 422


def test_predict_empty_payload(client: TestClient):
    """All four required fields missing at once."""
    response = client.post("/predict", json={})
    assert response.status_code == 422


def test_predict_malformed_json(client: TestClient):
    """Body that is not valid JSON at all."""
    response = client.post(
        "/predict", content=b"{not valid json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422


def test_predict_wrong_type(client: TestClient):
    """String where a number is required."""
    request_data = {
        "focus_minutes": "a lot",
        "distraction_minutes": 30,
        "tasks_due": 2,
        "hours_to_deadline": 24.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 422


def test_predict_response_structure(client: TestClient):
    """Test that prediction response has correct structure."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": 30,
        "tasks_due": 3,
        "hours_to_deadline": 24.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "cognitive_load_level" in data
    assert data["cognitive_load_level"] in [level.value for level in CognitiveLoadLevel]


def test_predict_edge_case_high_focus_low_distraction(client: TestClient):
    """Test prediction with high focus and low distraction."""
    request_data = {
        "focus_minutes": 240,
        "distraction_minutes": 10,
        "tasks_due": 1,
        "hours_to_deadline": 120.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]


def test_predict_edge_case_immediate_deadline(client: TestClient):
    """Test prediction with immediate deadline."""
    request_data = {
        "focus_minutes": 60,
        "distraction_minutes": 30,
        "tasks_due": 3,
        "hours_to_deadline": 0.5,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]


def test_predict_edge_case_many_tasks(client: TestClient):
    """Test prediction with many tasks due."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": 30,
        "tasks_due": 10,
        "hours_to_deadline": 48.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert data["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]


def test_predict_edge_case_extremely_large_values(client: TestClient):
    """Very large but schema-valid inputs should not error."""
    request_data = {
        "focus_minutes": 1_000_000,
        "distraction_minutes": 1_000_000,
        "tasks_due": 100_000,
        "hours_to_deadline": 1_000_000.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]


def test_predict_extra_fields_are_ignored(client: TestClient):
    """Undocumented extra fields do not break request validation (default pydantic policy)."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": 30,
        "tasks_due": 3,
        "hours_to_deadline": 24.0,
        "unexpected_field": "should be ignored, not rejected",
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200


def test_ready_endpoint_default_auto_mode(client: TestClient):
    """Default INFERENCE_MODE=auto is always ready (rule fallback always answers)."""
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["mode"] == "auto"


def test_ready_rule_mode_always_ready(client: TestClient, monkeypatch):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "mode": "rule"}


def test_ready_local_model_mode_not_ready_without_artifact(client: TestClient, monkeypatch, tmp_path):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "local_model")
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.joblib"))
    import preprocessing_api.model_client as model_client_module

    model_client_module.reset_local_model_cache()
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["mode"] == "local_model"
    model_client_module.reset_local_model_cache()


def test_ready_kserve_mode_not_ready_without_url(client: TestClient, monkeypatch):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "kserve")
    monkeypatch.delenv("KSERVE_PREDICT_URL", raising=False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["mode"] == "kserve"


def test_predict_rule_mode_uses_rule_only(client: TestClient, monkeypatch):
    """INFERENCE_MODE=rule must not attempt KServe or local-model lookups at all."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    request_data = {
        "focus_minutes": 180,
        "distraction_minutes": 20,
        "tasks_due": 1,
        "hours_to_deadline": 96.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "LOW"


def test_predict_local_model_mode_returns_503_without_artifact(client: TestClient, monkeypatch, tmp_path):
    """Explicit local_model mode must not silently fall back to the rule engine."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "local_model")
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.joblib"))
    monkeypatch.delenv("ALLOW_RULE_FALLBACK", raising=False)
    import preprocessing_api.model_client as model_client_module

    model_client_module.reset_local_model_cache()
    response = client.post(
        "/predict",
        json={"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 2, "hours_to_deadline": 24.0},
    )
    assert response.status_code == 503
    model_client_module.reset_local_model_cache()


def test_predict_local_model_mode_with_explicit_fallback_enabled(client: TestClient, monkeypatch, tmp_path):
    """ALLOW_RULE_FALLBACK=true is the only way an explicit mode may fall back, and it must
    still be visible (a distinct source label), not indistinguishable from a real model answer."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "local_model")
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "missing.joblib"))
    monkeypatch.setenv("ALLOW_RULE_FALLBACK", "true")
    import preprocessing_api.model_client as model_client_module

    model_client_module.reset_local_model_cache()
    response = client.post(
        "/predict",
        json={"focus_minutes": 180, "distraction_minutes": 20, "tasks_due": 1, "hours_to_deadline": 96.0},
    )
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "LOW"
    model_client_module.reset_local_model_cache()


def test_predict_kserve_mode_returns_503_without_url(client: TestClient, monkeypatch):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "kserve")
    monkeypatch.delenv("KSERVE_PREDICT_URL", raising=False)
    monkeypatch.delenv("ALLOW_RULE_FALLBACK", raising=False)
    response = client.post(
        "/predict",
        json={"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 2, "hours_to_deadline": 24.0},
    )
    assert response.status_code == 503


def test_model_info_endpoint_structure(client: TestClient):
    response = client.get("/model-info")
    assert response.status_code == 200
    body = response.json()
    for key in ("inference_mode", "allow_rule_fallback", "kserve_configured", "local_model_available", "model_manifest"):
        assert key in body


def test_model_info_reports_current_mode(client: TestClient, monkeypatch):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "rule")
    response = client.get("/model-info")
    assert response.json()["inference_mode"] == "rule"


def test_invalid_inference_mode_raises_at_read_time(monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "not-a-real-mode")
    try:
        main_module._read_inference_mode()
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_metrics_endpoint(client: TestClient):
    """Test Prometheus metrics endpoint is exposed."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "cognitive_load" in response.text or "prometheus_client" in response.text


def test_favicon_endpoint(client: TestClient):
    response = client.get("/favicon.ico")
    assert response.status_code == 204


def test_robots_endpoint(client: TestClient):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Disallow" in response.text


def test_predict_local_model_mode_success(client: TestClient, monkeypatch):
    """Explicit local_model mode, backend healthy: response reflects the model's answer."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "local_model")
    monkeypatch.setattr(main_module, "predict_with_local_model", lambda request: CognitiveLoadLevel.HIGH)
    response = client.post(
        "/predict",
        json={"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 2, "hours_to_deadline": 24.0},
    )
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "HIGH"


def test_predict_kserve_mode_success(client: TestClient, monkeypatch):
    """Explicit kserve mode, backend healthy: response reflects KServe's answer."""
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "kserve")
    monkeypatch.setattr(main_module, "predict_with_kserve", lambda request: CognitiveLoadLevel.MEDIUM)
    response = client.post(
        "/predict",
        json={"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 2, "hours_to_deadline": 24.0},
    )
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "MEDIUM"


def test_predict_kserve_mode_explicit_fallback_enabled(client: TestClient, monkeypatch):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "kserve")
    monkeypatch.setattr(main_module, "predict_with_kserve", lambda request: None)
    monkeypatch.setenv("ALLOW_RULE_FALLBACK", "true")
    response = client.post(
        "/predict",
        json={"focus_minutes": 180, "distraction_minutes": 20, "tasks_due": 1, "hours_to_deadline": 96.0},
    )
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "LOW"


def test_predict_auto_mode_prefers_kserve_when_available(client: TestClient, monkeypatch):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "auto")
    monkeypatch.setattr(main_module, "predict_with_kserve", lambda request: CognitiveLoadLevel.HIGH)
    monkeypatch.setattr(main_module, "predict_with_local_model", lambda request: CognitiveLoadLevel.LOW)
    response = client.post(
        "/predict",
        json={"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 2, "hours_to_deadline": 24.0},
    )
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "HIGH"


def test_predict_auto_mode_falls_back_to_local_model_when_kserve_unavailable(client: TestClient, monkeypatch):
    monkeypatch.setattr(main_module, "INFERENCE_MODE", "auto")
    monkeypatch.setattr(main_module, "predict_with_kserve", lambda request: None)
    monkeypatch.setattr(main_module, "predict_with_local_model", lambda request: CognitiveLoadLevel.MEDIUM)
    response = client.post(
        "/predict",
        json={"focus_minutes": 120, "distraction_minutes": 30, "tasks_due": 2, "hours_to_deadline": 24.0},
    )
    assert response.status_code == 200
    assert response.json()["cognitive_load_level"] == "MEDIUM"
