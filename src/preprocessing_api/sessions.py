"""Authenticated focus-session lifecycle and effort-label routes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from cogniflow_contracts import BehavioralActivityEvent, EffortLabelEvent, SessionLifecycleEvent
from cogniflow_sessions import ConflictError, FocusSessionRepository, NotFoundError
from preprocessing_api.security import authenticated_owner

router = APIRouter(prefix="/sessions", tags=["focus-sessions"])
SessionId = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")]


@lru_cache(maxsize=1)
def get_session_repository() -> FocusSessionRepository:
    return FocusSessionRepository()


def _server_ingested(
    event: SessionLifecycleEvent | EffortLabelEvent | BehavioralActivityEvent,
):
    now = datetime.now(UTC)
    if event.event_time > now:
        raise HTTPException(422, "event_time cannot be in the future")
    return event.model_copy(update={"ingested_at": now})


def _raise_repository_error(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ConflictError):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, sqlite3.Error):
        raise HTTPException(503, "Focus-session store is unavailable") from exc
    raise exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(event: SessionLifecycleEvent, response: Response,
                   owner: str = Depends(authenticated_owner),
                   repository: FocusSessionRepository = Depends(get_session_repository)):
    try:
        result, created = repository.create(_server_ingested(event), owner)
    except (ConflictError, sqlite3.Error) as exc:
        _raise_repository_error(exc)
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.post("/{session_id}/transitions")
async def transition_session(session_id: SessionId, event: SessionLifecycleEvent,
                       owner: str = Depends(authenticated_owner),
                       repository: FocusSessionRepository = Depends(get_session_repository)):
    if event.session_id != session_id:
        raise HTTPException(422, "Path and event session IDs must match")
    try:
        return repository.transition(_server_ingested(event), owner)[0]
    except (ConflictError, NotFoundError, sqlite3.Error) as exc:
        _raise_repository_error(exc)


@router.post("/{session_id}/labels", status_code=status.HTTP_201_CREATED)
async def add_label(session_id: SessionId, event: EffortLabelEvent, response: Response,
              owner: str = Depends(authenticated_owner),
              repository: FocusSessionRepository = Depends(get_session_repository)):
    if event.session_id != session_id:
        raise HTTPException(422, "Path and event session IDs must match")
    try:
        result, created = repository.add_label(_server_ingested(event), owner)
    except (ConflictError, NotFoundError, sqlite3.Error) as exc:
        _raise_repository_error(exc)
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.post("/{session_id}/activity-windows", status_code=status.HTTP_201_CREATED)
async def add_activity_window(
    session_id: SessionId, event: BehavioralActivityEvent, response: Response,
    owner: str = Depends(authenticated_owner),
    repository: FocusSessionRepository = Depends(get_session_repository),
):
    if event.session_id != session_id:
        raise HTTPException(422, "Path and event session IDs must match")
    try:
        result, created = repository.add_activity(_server_ingested(event), owner)
    except (ConflictError, NotFoundError, sqlite3.Error) as exc:
        _raise_repository_error(exc)
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/{session_id}")
async def get_session(session_id: SessionId, owner: str = Depends(authenticated_owner),
                repository: FocusSessionRepository = Depends(get_session_repository)):
    try:
        return repository.session(session_id, owner)
    except (NotFoundError, sqlite3.Error) as exc:
        _raise_repository_error(exc)


@router.get("/{session_id}/timeline")
async def get_timeline(session_id: SessionId, owner: str = Depends(authenticated_owner),
                 limit: Annotated[int, Query(ge=1, le=100)] = 50,
                 offset: Annotated[int, Query(ge=0)] = 0,
                 repository: FocusSessionRepository = Depends(get_session_repository)):
    try:
        return repository.timeline(session_id, owner, limit, offset)
    except (NotFoundError, sqlite3.Error) as exc:
        _raise_repository_error(exc)
