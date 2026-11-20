from scripts import collect_module2_gold_evidence as evidence


class Paginator:
    def paginate(self, **kwargs):
        assert kwargs == {"Bucket": "lake", "Prefix": "metastore/gold/"}
        return [{"Contents": [{"Size": 10}, {"Size": 7}]}, {}]


class S3:
    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return Paginator()


def test_collect_uses_delta_object_prefix_for_physical_bytes(monkeypatch) -> None:
    monkeypatch.setattr(evidence, "query", lambda _endpoint, _sql: [[3]])
    result = evidence.collect("http://trino", S3(), "lake")
    assert result["accepted_rows"] == 3
    assert result["gold_physical_bytes"] == 17
    assert set(result["table_rows"]) == set(evidence.GOLD_TABLES)
