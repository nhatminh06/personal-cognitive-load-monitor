"""FastAPI event-ingestion router."""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException, status
from prometheus_client import Counter

from cogniflow_data.events import EventAccepted, SESSION_TOPIC, SessionEvent
from cogniflow_data.kafka import EventPublisher, KafkaPublisher, PublishError
from cogniflow_data.online import OnlineFeatureRecord, OnlineFeatureStore, RedisFeatureStore

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


async def authorize_event(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("EVENT_API_KEY")
    if expected and (x_api_key is None or not hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@router.post("/events", response_model=EventAccepted, status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(
    event: SessionEvent,
    _: None = Depends(authorize_event),
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
    session_id: str,
    store: OnlineFeatureStore = Depends(feature_store_dependency),
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
