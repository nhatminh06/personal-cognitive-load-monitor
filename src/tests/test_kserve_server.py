"""Adapter checks against the pinned KServe ModelServer SDK."""

import asyncio

import pytest
from fastapi import HTTPException
from kserve import ModelRepository
from kserve.errors import InvalidInput, ModelNotReady
from kserve.protocol.dataplane import DataPlane
from kserve.protocol.rest.v1_endpoints import V1Endpoints

from cogniflow_kserve import server
from scripts.serve_engineering_model import _invalid_input_handler


def test_metadata_endpoint_returns_only_loaded_verified_provenance(monkeypatch):
    provenance = {"model_name": "classifier", "approval_status": "approved"}
    model = server.CogniFlowModel("classifier")
    model.ready = True
    model.predictor.provenance = provenance
    monkeypatch.setattr(server, "model", model)

    assert asyncio.run(server.metadata("classifier")) == provenance
    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.metadata("other"))
    assert exc.value.status_code == 503


def test_kserve_020_liveness_and_model_readiness_contract():
    model = server.CogniFlowModel("classifier")
    repository = ModelRepository()
    repository.update(model)
    dataplane = DataPlane(model_registry=repository)
    endpoints = V1Endpoints(dataplane)

    assert asyncio.run(dataplane.live()) == {"status": "alive"}
    with pytest.raises(ModelNotReady):
        asyncio.run(endpoints.model_ready("classifier"))

    model.ready = True
    assert asyncio.run(endpoints.model_ready("classifier")) == {
        "name": "classifier",
        "ready": True,
    }


def test_engineering_invalid_input_handler_returns_bounded_client_error():
    response = asyncio.run(_invalid_input_handler(None, InvalidInput("invalid fixture")))

    assert response.status_code == 400
    assert response.body == b'{"error":"invalid fixture"}'


def test_prediction_creates_safe_inference_span(monkeypatch):
    recorded = {}

    class Span:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class Tracer:
        def start_as_current_span(self, name, *, attributes):
            recorded.update(name=name, attributes=attributes)
            return Span()

    model = server.CogniFlowModel("classifier")
    monkeypatch.setattr(server, "TRACER", Tracer())
    monkeypatch.setattr(model.predictor, "predict", lambda payload: {"predictions": ["LOW"]})

    assert model.predict({"instances": [[1, 2, 3, 4, 5, 6]]}) == {"predictions": ["LOW"]}
    assert recorded == {
        "name": "cogniflow.model.predict",
        "attributes": {"cogniflow.model.name": "classifier"},
    }
