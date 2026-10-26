from datetime import UTC, datetime
from random import Random

import json

import pytest

from scripts.generate_session_events import event, event_bytes, main


def test_generator_is_deterministic_and_contract_valid():
    first = event(4, Random(42), datetime(2026, 1, 1, tzinfo=UTC))
    second = event(4, Random(42), datetime(2026, 1, 1, tzinfo=UTC))
    assert first.wire_bytes() == second.wire_bytes()
    assert first.session_id == "synthetic-004"


def test_generator_fault_fixtures_are_deterministic():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    normal = json.loads(event_bytes(1, 42, start))
    late = json.loads(event_bytes(1, 42, start, late_every=2, late_by_seconds=30))
    invalid = json.loads(event_bytes(1, 42, start, invalid=True))
    assert late["event_time"] < normal["event_time"]
    assert invalid["payload"]["focus_minutes"] == -1
    assert event_bytes(1, 42, start) == event_bytes(1, 42, start)


def test_generator_enforces_size_and_can_resume(tmp_path, monkeypatch):
    output = tmp_path / "events.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        ["generator", "--count", "2", "--output", str(output), "--min-free-bytes", "0"],
    )
    main()
    first = output.read_bytes()
    monkeypatch.setattr(
        "sys.argv",
        ["generator", "--count", "3", "--output", str(output), "--min-free-bytes", "0", "--resume"],
    )
    main()
    assert output.read_bytes().startswith(first)
    assert len(output.read_text().splitlines()) == 3

    monkeypatch.setattr(
        "sys.argv",
        ["generator", "--count", "1", "--output", str(tmp_path / "small"),
         "--max-bytes", "1", "--min-free-bytes", "0"],
    )
    with pytest.raises(RuntimeError, match="maximum output size"):
        main()
