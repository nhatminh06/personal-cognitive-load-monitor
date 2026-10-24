"""Portable parity vectors for batch and streaming engines."""

import json
from pathlib import Path

import pytest

from preprocessing_api.features import feature_vector


@pytest.mark.parametrize(
    "case",
    json.loads((Path(__file__).parents[2] / "tests/fixtures/feature_vectors.json").read_text()),
)
def test_shared_feature_contract_vectors(case):
    assert feature_vector(case["input"]) == pytest.approx(case["expected"], abs=1e-12)
