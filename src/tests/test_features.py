import pytest

from preprocessing_api.features import FEATURE_NAMES, feature_vector


def test_feature_contract_order_and_zero_total():
    assert FEATURE_NAMES[-2:] == ("focus_ratio", "distraction_ratio")
    assert feature_vector({"focus_minutes": 0, "distraction_minutes": 0, "tasks_due": 2, "hours_to_deadline": 4}) == [0.0, 0.0, 2.0, 4.0, 0.0, 0.0]


def test_feature_ratios_are_stable_for_long_sessions():
    result = feature_vector({"focus_minutes": 900, "distraction_minutes": 100, "tasks_due": 1, "hours_to_deadline": 87600})
    assert result[4:] == pytest.approx([0.9, 0.1])
