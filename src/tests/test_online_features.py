import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from cogniflow_data.api import online_features
from cogniflow_data.online import OnlineFeatureRecord, RedisFeatureStore


class Store:
    def __init__(self, value=None, error=False):
        self.value, self.error = value, error

    def get(self, _session_id):
        if self.error:
            raise ConnectionError
        return self.value


def record(at: datetime) -> OnlineFeatureRecord:
    return OnlineFeatureRecord(
        session_id="session-1", feature_timestamp=at, schema_version="1.0",
        provenance="flink:kafka:cogniflow.session-events.v1", focus_minutes=45,
        distraction_minutes=15, tasks_due=2, hours_to_deadline=24,
        focus_ratio=0.75, distraction_ratio=0.25,
    )


def test_online_features_returns_timestamped_contract():
    result = asyncio.run(online_features("session-1", Store(record(datetime.now(UTC)))))
    assert result.focus_ratio == 0.75


def test_online_features_missing_stale_and_unavailable():
    for store, status in (
        (Store(), 404),
        (Store(record(datetime.now(UTC) - timedelta(hours=1))), 503),
        (Store(error=True), 503),
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(online_features("session-1", store))
        assert error.value.status_code == status


def test_redis_adapter_projects_flink_window_metadata() -> None:
    expected = record(datetime.now(UTC))
    payload = expected.model_dump_json().removesuffix("}")
    payload += ',"window_type":"rolling","window_start":"2026-01-01T00:00:00Z",'
    payload += '"window_end":"2026-01-01T00:05:00Z","event_count":2,"feature_schema_version":"1.0"}'
    store = RedisFeatureStore.__new__(RedisFeatureStore)
    store.client = type("Client", (), {"get": lambda self, key: payload.encode()})()
    store._redis_error = RuntimeError
    assert store.get("session-1") == expected
