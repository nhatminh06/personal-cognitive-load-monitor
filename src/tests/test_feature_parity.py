"""Portable parity vectors for batch and streaming engines."""

import json
from pathlib import Path

import pytest

from preprocessing_api.features import FEATURE_NAMES, feature_vector

UNITS = ["minutes", "minutes", "count", "hours", "ratio", "ratio"]


@pytest.mark.parametrize(
    "case",
    json.loads((Path(__file__).parents[2] / "tests/fixtures/feature_vectors.json").read_text()),
)
def test_shared_feature_contract_vectors(case):
    assert case["feature_schema_version"] == "1.0"
    assert tuple(case["feature_names"]) == FEATURE_NAMES
    assert case["units"] == UNITS
    assert case["event_time"].endswith("Z")
    assert feature_vector(case["input"]) == pytest.approx(case["expected"], abs=1e-12)


@pytest.mark.parametrize("invalid", [None, {}, {"focus_minutes": None}])
def test_feature_contract_rejects_null_or_incomplete_input(invalid):
    with pytest.raises((KeyError, TypeError)):
        feature_vector(invalid)
