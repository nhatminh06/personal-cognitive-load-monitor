from __future__ import annotations

import pytest

from cogniflow_data.trino_history import TrinoHistoryReader


def test_reader_pins_delta_version_and_returns_history(monkeypatch):
    reader = TrinoHistoryReader()
    calls = []

    def query(sql):
        calls.append(sql)
        return [{"version": 1, "timestamp": "2026-01-01T00:00:00Z", "operation": "MERGE"}] if "$history" in sql else [{"event_id": "event"}]

    monkeypatch.setattr(reader, "query", query)
    history, rows = reader.snapshot(1)
    assert history["version"] == 1 and rows == [{"event_id": "event"}]
    assert "to_iso8601(timestamp)" in calls[0]
    assert "to_iso8601(event_time)" in calls[1]
    assert "FOR VERSION AS OF 1" in calls[1]


def test_reader_restricts_endpoint_and_version():
    with pytest.raises(ValueError, match="restricted"):
        TrinoHistoryReader("http://trino:8080")
    with pytest.raises(ValueError, match="non-negative"):
        TrinoHistoryReader().snapshot(-1)
    with pytest.raises(ValueError, match="non-negative"):
        TrinoHistoryReader().snapshot(1.5)  # type: ignore[arg-type]
