from datetime import UTC, datetime
from random import Random

from scripts.generate_session_events import event


def test_generator_is_deterministic_and_contract_valid():
    first = event(4, Random(42), datetime(2026, 1, 1, tzinfo=UTC))
    second = event(4, Random(42), datetime(2026, 1, 1, tzinfo=UTC))
    assert first.wire_bytes() == second.wire_bytes()
    assert first.session_id == "synthetic-004"
