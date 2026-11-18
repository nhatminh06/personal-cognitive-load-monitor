import json

import pytest

from scripts.validate_kserve_gateways import validate_gateway_refs


def _config(ingress: str = "istio-system/istio-ingressgateway"):
    return {"data": {"ingress": json.dumps({
        "ingressGateway": ingress,
        "localGateway": "knative-serving/knative-local-gateway",
    })}}


def _gateways():
    return {"items": [
        {"kind": "Gateway", "metadata": {
            "namespace": "istio-system", "name": "istio-ingressgateway",
        }},
        {"kind": "Gateway", "metadata": {
            "namespace": "knative-serving", "name": "knative-local-gateway",
        }},
    ]}


def test_gateway_contract_accepts_exact_existing_references():
    validate_gateway_refs(
        _config(), _gateways(),
        expected_ingress="istio-system/istio-ingressgateway",
        expected_local="knative-serving/knative-local-gateway",
    )


def test_gateway_contract_rejects_missing_configured_gateway():
    with pytest.raises(ValueError, match="does not exist"):
        validate_gateway_refs(
            _config("kubeflow/kubeflow-gateway"), _gateways(),
            expected_ingress="kubeflow/kubeflow-gateway",
            expected_local="knative-serving/knative-local-gateway",
        )


def test_gateway_contract_rejects_unexpected_gateway_selection():
    with pytest.raises(ValueError, match="do not match expected"):
        validate_gateway_refs(
            _config(), _gateways(),
            expected_ingress="kubeflow/kubeflow-gateway",
            expected_local="knative-serving/knative-local-gateway",
        )
