import pytest

from scripts import collect_module2_gold_evidence as evidence


class Paginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **kwargs):
        assert kwargs == {"Bucket": "lake", "Prefix": "metastore/gold/"}
        return iter(self.pages)


class S3:
    def __init__(self, pages):
        self.pages = pages

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return Paginator(self.pages)


def test_collect_counts_all_gold_prefix_objects_across_pages(monkeypatch) -> None:
    def query(_endpoint, sql):
        if "accepted_rows" in sql:
            return [[3]]
        return [[2 if sql.endswith("gold_session_summary") else 1]]

    monkeypatch.setattr(evidence, "query", query)
    pages = [
        {"Contents": [
            {"Key": "metastore/gold/gold_session_summary/data.parquet", "Size": 10},
            {"Key": "metastore/gold/gold_daily_focus_metrics/data.parquet", "Size": 7},
            {"Key": "metastore/gold/old_run/stale.parquet", "Size": 5},
        ]},
        {"Contents": [{"Key": "metastore/gold/unrelated.txt", "Size": 2}]},
    ]
    result = evidence.collect("http://trino", S3(pages), "lake")
    assert result["accepted_rows"] == 3
    assert result["table_rows"]["gold_session_summary"] == 2
    assert set(result["table_rows"]) == set(evidence.GOLD_TABLES)
    assert result["gold_prefix_object_bytes"] == 24


def test_collect_empty_prefix_is_zero(monkeypatch) -> None:
    monkeypatch.setattr(evidence, "query", lambda _endpoint, _sql: [[0]])
    assert evidence.collect("http://trino", S3([{}, {"Contents": []}]), "lake")["gold_prefix_object_bytes"] == 0


def test_collect_total_is_deterministic_when_pages_and_objects_reorder(monkeypatch) -> None:
    monkeypatch.setattr(evidence, "query", lambda _endpoint, _sql: [[0]])
    pages = [{"Contents": [{"Size": "13"}, {"Size": 4}]}, {"Contents": [{"Size": 9}]}]
    forward = evidence.collect("http://trino", S3(pages), "lake")
    backward = evidence.collect("http://trino", S3(list(reversed(pages))), "lake")
    assert forward["gold_prefix_object_bytes"] == backward["gold_prefix_object_bytes"] == 26


def test_collect_missing_size_and_object_store_failure_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(evidence, "query", lambda _endpoint, _sql: [[0]])
    with pytest.raises(KeyError):
        evidence.collect("http://trino", S3([{"Contents": [{"Key": "missing-size"}]}]), "lake")

    class BrokenS3:
        def get_paginator(self, _name):
            raise RuntimeError("object store unavailable")

    with pytest.raises(RuntimeError, match="object store unavailable"):
        evidence.collect("http://trino", BrokenS3(), "lake")

    class BrokenPageS3:
        def get_paginator(self, _name):
            class BrokenPaginator:
                def paginate(self, **_kwargs):
                    yield {"Contents": [{"Size": 1}]}
                    raise RuntimeError("pagination interrupted")

            return BrokenPaginator()

    with pytest.raises(RuntimeError, match="pagination interrupted"):
        evidence.collect("http://trino", BrokenPageS3(), "lake")
