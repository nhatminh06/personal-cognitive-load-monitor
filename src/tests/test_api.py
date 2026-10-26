"""Tests for the cognitive load prediction API."""

from typing import Any

from preprocessing_api.schemas import CognitiveLoadLevel

TestClient = Any


def test_root_endpoint(client):
    """Test root endpoint serves the actual prediction demo."""
    response = client.get("/")
    assert response.status_code == 200
    assert "CogniFlow" in response.text
    assert "fetch('/predict'" in response.text


def test_health_endpoint(client):
    """Test health endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_predict_low_cognitive_load(client: TestClient):
    """Test prediction with low cognitive load scenario."""
    request_data = {
        "focus_minutes": 180,
        "distraction_minutes": 20,
        "tasks_due": 1,
        "hours_to_deadline": 96.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "cognitive_load_level" in data
    assert data["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]
    assert data["inference_source"] == "demo_rule"
    assert data["is_fallback"] is False


def test_predict_medium_cognitive_load(client: TestClient):
    """Test prediction with medium cognitive load scenario."""
    request_data = {
        "focus_minutes": 120,
        "distraction_minutes": 30,
        "tasks_due": 3,
        "hours_to_deadline": 48.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "cognitive_load_level" in data
    assert data["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]


def test_predict_high_cognitive_load(client: TestClient):
    """Test prediction with high cognitive load scenario."""
    request_data = {
        "focus_minutes": 60,
        "distraction_minutes": 60,
        "tasks_due": 5,
        "hours_to_deadline": 12.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "cognitive_load_level" in data
    assert data["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]


def test_predict_with_zero_focus_and_distraction(client: TestClient):
    """Test prediction with zero focus and distraction minutes."""
    request_data = {
        "focus_minutes": 0,
        "distraction_minutes": 0,
        "tasks_due": 2,
        "hours_to_deadline": 24.0,
    }
    response = client.post("/predict", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "cognitive_load_level" in data
    assert data["cognitive_load_level"] in ["LOW", "MEDIUM", "HIGH"]


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



def test_ready_endpoint(client: TestClient):
    """Test readiness endpoint."""
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_model_info_demo_provenance(client: TestClient):
    response = client.get("/model-info")
    assert response.status_code == 200
    assert response.json() == {
        "inference_mode": "demo_rule",
        "model_version": None,
        "label_provenance": "synthetic_proxy",
    }


def test_model_info_exposes_local_model_lineage(client: TestClient, monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "local_model")
    provenance = {
        "model_version": "7",
        "model_name": "cognitive-load-classifier-phase2",
        "dataset_sha256": "1" * 64,
        "feature_schema_version": "1.0",
        "feature_names": ["focus_minutes", "distraction_minutes", "tasks_due", "hours_to_deadline", "focus_ratio", "distraction_ratio"],
        "registered_artifact_sha256": "2" * 64,
        "packaged_model_sha256": "3" * 64,
        "label_provenance": "synthetic_proxy",
        "run_id": "run-1",
        "git_revision": "4" * 40,
    }
    monkeypatch.setattr("preprocessing_api.main.verified_local_model_provenance", lambda: provenance)
    response = client.get("/model-info")
    assert response.status_code == 200
    assert response.json() == {
        "inference_mode": "local_model",
        "model_version": "7",
        "label_provenance": "synthetic_proxy",
        "model_name": "cognitive-load-classifier-phase2",
        "dataset_sha256": "1" * 64,
        "feature_schema_version": "1.0",
        "feature_names": provenance["feature_names"],
        "registered_artifact_sha256": "2" * 64,
        "packaged_model_sha256": "3" * 64,
        "run_id": "run-1",
        "git_revision": "4" * 40,
    }


def test_model_info_fails_closed_without_verified_provenance(client: TestClient, monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "local_model")
    monkeypatch.setattr("preprocessing_api.main.verified_local_model_provenance", lambda: None)
    response = client.get("/model-info")
    assert response.status_code == 503
    assert response.json() == {"detail": "Verified model provenance is unavailable"}


def test_invalid_inference_mode_fails_closed(client: TestClient, monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "surprise")
    response = client.post("/predict", json={
        "focus_minutes": 1, "distraction_minutes": 1, "tasks_due": 1,
        "hours_to_deadline": 1,
    })
    assert response.status_code == 500


def test_kserve_failure_does_not_fallback(client: TestClient, monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "kserve")
    monkeypatch.setenv("KSERVE_PREDICT_URL", "http://model.invalid")
    monkeypatch.setattr("preprocessing_api.main.predict_with_kserve", lambda request: (_ for _ in ()).throw(ConnectionError()))
    response = client.post("/predict", json={
        "focus_minutes": 1, "distraction_minutes": 1, "tasks_due": 1,
        "hours_to_deadline": 1,
    })
    assert response.status_code == 503
    assert response.json() == {"detail": "Model server is unavailable"}


def test_kserve_readiness_and_model_info_require_verified_provenance(
    client: TestClient, monkeypatch
):
    monkeypatch.setenv("INFERENCE_MODE", "kserve")
    provenance = {
        "model_version": "7",
        "label_provenance": "synthetic_proxy",
        "model_name": "classifier",
        "dataset_sha256": "1" * 64,
        "feature_schema_version": "1.0",
        "feature_names": ["a", "b", "c", "d", "e", "f"],
        "registered_artifact_sha256": "2" * 64,
        "packaged_model_sha256": "3" * 64,
        "run_id": "run-1",
        "git_revision": "4" * 40,
    }
    monkeypatch.setattr(
        "preprocessing_api.main.verified_kserve_provenance", lambda: provenance
    )
    assert client.get("/ready").json() == {"status": "ready", "inference_mode": "kserve"}
    assert client.get("/model-info").json()["registered_artifact_sha256"] == "2" * 64

    monkeypatch.setattr(
        "preprocessing_api.main.verified_kserve_provenance",
        lambda: (_ for _ in ()).throw(ConnectionError()),
    )
    assert client.get("/ready").status_code == 503
    assert client.get("/model-info").status_code == 503


def test_local_model_failure_does_not_fallback(client: TestClient, monkeypatch):
    monkeypatch.setenv("INFERENCE_MODE", "local_model")
    monkeypatch.setattr("preprocessing_api.main.predict_with_local_model", lambda request: None)
    request = {
        "focus_minutes": 1,
        "distraction_minutes": 1,
        "tasks_due": 1,
        "hours_to_deadline": 1,
    }
    assert client.get("/ready").status_code == 503
    response = client.post("/predict", json=request)
    assert response.status_code == 503
    assert response.json() == {"detail": "Configured local model is unavailable"}


def test_metrics_endpoint(client: TestClient):
    """Test Prometheus metrics endpoint is exposed."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "cognitive_load" in response.text or "prometheus_client" in response.text


def test_api_docs_csp_allows_fastapi_assets(client: TestClient):
    response = client.get("/docs")
    assert response.status_code == 200
    assert "SwaggerUIBundle" in response.text
    docs_csp = response.headers["content-security-policy"]
    assert "https://cdn.jsdelivr.net" in docs_csp
    assert "script-src 'self' 'unsafe-inline'" in docs_csp


def test_security_headers_and_request_size_limit(client: TestClient):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "cdn.jsdelivr.net" not in response.headers["content-security-policy"]

    response = client.post(
        "/predict",
        content=b"x" * (1024 * 1024 + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_production_prediction_authentication_fails_closed(client: TestClient, monkeypatch):
    payload = {
        "focus_minutes": 1,
        "distraction_minutes": 1,
        "tasks_due": 1,
        "hours_to_deadline": 1,
    }
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("COGNIFLOW_API_KEY", raising=False)
    monkeypatch.delenv("EVENT_API_KEY", raising=False)
    assert client.post("/predict", json=payload).status_code == 503

    monkeypatch.setenv("COGNIFLOW_API_KEY", "test-secret")
    assert client.post("/predict", json=payload).status_code == 401
    assert client.post(
        "/predict", json=payload, headers={"x-api-key": "test-secret"}
    ).status_code == 200
