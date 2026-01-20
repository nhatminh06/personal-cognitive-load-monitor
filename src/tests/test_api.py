"""Tests for the cognitive load prediction API."""

from fastapi.testclient import TestClient

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

