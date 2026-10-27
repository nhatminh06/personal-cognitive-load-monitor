"""Adapter checks against the pinned KServe ModelServer SDK."""

import asyncio

import pytest
from fastapi import HTTPException
from kserve import ModelRepository
from kserve.errors import ModelNotReady
from kserve.protocol.dataplane import DataPlane
from kserve.protocol.rest.v1_endpoints import V1Endpoints

from cogniflow_kserve import server


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
