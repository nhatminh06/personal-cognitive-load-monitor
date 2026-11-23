"""Offline contracts for the retained independent Silver fixture and dbt project."""

from collections import Counter
import hashlib
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import yaml


ROOT = Path(__file__).parents[2]
FIXTURE = ROOT / "tests/fixtures/module2_session_features.parquet"
FIXTURE_SHA256 = "85aa6318227dcf7ce01d3cb0218114bc761d66779957795fbf5b86893d074961"


def test_qualified_silver_fixture_oracle() -> None:
    assert FIXTURE.is_file(), f"Missing tracked synthetic fixture: {FIXTURE}"
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256
    table = pq.read_table(FIXTURE)
    rows = table.to_pylist()
    assert table.num_rows == 3
    assert len(table.schema) == 18
    assert [row["event_id"] for row in rows] == ["event-a1", "event-a2", "event-b1"]
    assert len({row["event_id"] for row in rows}) == 3
    assert sum(row["focus_minutes"] for row in rows) == 135
    assert sum(row["user_id"] is None for row in rows) == 1
    assert Counter(row["session_id"] for row in rows) == {"session-a": 2, "session-b": 1}
    assert sum(row["focus_minutes"] for row in rows if row["session_id"] == "session-a") == 75
    assert sum(row["focus_ratio"] for row in rows) / 3 == 0.8333333333333334


def test_missing_fixture_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setitem(globals(), "FIXTURE", tmp_path / "missing.parquet")
    with pytest.raises(AssertionError, match="Missing tracked synthetic fixture"):
        test_qualified_silver_fixture_oracle()


def test_qualified_dbt_contracts() -> None:
    models = ROOT / "analytics/models"
    gold = sorted((models / "gold").glob("*.sql"))
    assert len(gold) == 6
    for path in gold:
        sql = path.read_text()
        assert "materialized='incremental'" in sql
        assert "incremental_strategy='merge'" in sql
        assert "unique_key=" in sql
    assert len(list((models / "staging").glob("*.sql"))) == 1
    schema = yaml.safe_load((models / "schema.yml").read_text())
    sources = yaml.safe_load((models / "sources.yml").read_text())
    declared = sum(len(column.get("tests", [])) for model in schema["models"] for column in model.get("columns", []))
    declared += sum(len(column.get("tests", [])) for source in sources["sources"] for table in source["tables"] for column in table.get("columns", []))
    assert declared == 8
    quality = (models / "gold/gold_data_quality_summary.sql").read_text()
    assert "count(*) as accepted_rows" in quality
    assert "count_if(event_time < current_timestamp - interval '7' day) as stale_rows" in quality
