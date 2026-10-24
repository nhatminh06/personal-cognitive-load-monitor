"""FastAPI event-ingestion router."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Path, status
from prometheus_client import Counter

from cogniflow_data.events import EventAccepted, SESSION_TOPIC, SessionEvent
from cogniflow_data.kafka import EventPublisher, KafkaPublisher, PublishError
from cogniflow_data.online import OnlineFeatureRecord, OnlineFeatureStore, RedisFeatureStore
from preprocessing_api.security import require_api_key

router = APIRouter(tags=["data-ingestion"])
EVENT_INGESTION = Counter(
    "cogniflow_events_total", "Validated event-ingestion outcomes.", ["outcome"]
)


@lru_cache(maxsize=1)
def get_event_publisher() -> EventPublisher:
    return KafkaPublisher()


async def event_publisher_dependency() -> EventPublisher:
    return get_event_publisher()


@lru_cache(maxsize=1)
def get_feature_store() -> OnlineFeatureStore:
    return RedisFeatureStore()


async def feature_store_dependency() -> OnlineFeatureStore:
    return get_feature_store()


@router.post("/events", response_model=EventAccepted, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    event: SessionEvent,
    _: None = Depends(require_api_key),
    publisher: EventPublisher = Depends(event_publisher_dependency),
) -> EventAccepted:
    """Validate and publish an event; never acknowledge an unavailable broker."""

    accepted_at = datetime.now(UTC)
    event = event.model_copy(update={"ingested_at": accepted_at})
    try:
        publisher.publish(event)
    except PublishError as exc:
        EVENT_INGESTION.labels("broker_unavailable").inc()
        raise HTTPException(status_code=503, detail="Event broker is unavailable") from exc
    EVENT_INGESTION.labels("accepted").inc()
    return EventAccepted(event_id=event.event_id, topic=SESSION_TOPIC, accepted_at=accepted_at)


@router.get("/features/{session_id}", response_model=OnlineFeatureRecord)
async def online_features(
    session_id: str = Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
    store: OnlineFeatureStore = Depends(feature_store_dependency),
    _: None = Depends(require_api_key),
) -> OnlineFeatureRecord:
    try:
        record = store.get(session_id)
    except ConnectionError as exc:
        raise HTTPException(status_code=503, detail="Online feature store is unavailable") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Online features are unavailable")
    max_age = timedelta(seconds=int(os.getenv("ONLINE_FEATURE_MAX_AGE_SECONDS", "300")))
    if datetime.now(UTC) - record.feature_timestamp > max_age:
        raise HTTPException(status_code=503, detail="Online features are stale")
    return record
