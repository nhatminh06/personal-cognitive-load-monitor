"""Adapter checks against the pinned KServe ModelServer SDK."""

import asyncio

import pytest
from fastapi import HTTPException

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
