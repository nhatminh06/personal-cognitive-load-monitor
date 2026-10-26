"""Explicit Redis adapter for timestamped Module II online features."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict


class OnlineFeatureRecord(BaseModel):
    session_id: str
    feature_timestamp: datetime
    schema_version: str
    provenance: str
    focus_minutes: int
    distraction_minutes: int
    tasks_due: int
    hours_to_deadline: float
    focus_ratio: float
    distraction_ratio: float

    model_config = ConfigDict(extra="forbid")


class OnlineFeatureStore(Protocol):
    def get(self, session_id: str) -> OnlineFeatureRecord | None: ...


class RedisFeatureStore:
    def __init__(self) -> None:
        try:
            import redis
        except ImportError as exc:
            raise ConnectionError("Redis client is not installed") from exc
        self._redis_error = redis.RedisError
        self.client: Any = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://:local-development-only@127.0.0.1:6379/0"),
            socket_connect_timeout=1,
            socket_timeout=1,
        )

    def get(self, session_id: str) -> OnlineFeatureRecord | None:
        try:
            value = cast(bytes | None, self.client.get(f"cogniflow:features:v1:{session_id}"))
        except self._redis_error as exc:
            raise ConnectionError("Redis unavailable") from exc
        return OnlineFeatureRecord.model_validate_json(value) if value else None
