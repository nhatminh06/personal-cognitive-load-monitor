"""Create a disposable aggregate-only focus-session HTTP smoke fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from cogniflow_contracts import BehavioralActivityEvent, CvFeatureWindowEvent, SessionLifecycleEvent
from cogniflow_sessions import FocusSessionRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--allow-synthetic-fixture", action="store_true")
    args = parser.parse_args()
    if not args.allow_synthetic_fixture:
        parser.error("synthetic serving fixture requires --allow-synthetic-fixture")
    key = os.getenv("COGNIFLOW_API_KEY")
    if not key or not key.strip():
        parser.error("set COGNIFLOW_API_KEY without placing it in command arguments")
    if args.database.exists() or args.requests.exists():
        parser.error("fixture outputs must not already exist")
    owner = hashlib.sha256(key.encode()).hexdigest()
    repository = FocusSessionRepository(args.database)
    start = datetime(2026, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
    end = start + timedelta(minutes=10)
    session_id = "synthetic-serving-fixture"
    repository.create(SessionLifecycleEvent(
        session_id=session_id, event_time=start, ingested_at=start,
        idempotency_key="fixture-start", event_type="session.started", sequence=1,
        session_kind="programming", privacy_mode="behavioral_cv",
        source="synthetic_fixture", producer_version="1.0.0",
    ), owner)
    repository.transition(SessionLifecycleEvent(
        session_id=session_id, event_time=end, ingested_at=end,
        idempotency_key="fixture-complete", event_type="session.completed", sequence=2,
        session_kind="programming", privacy_mode="behavioral_cv",
        source="synthetic_fixture", producer_version="1.0.0",
    ), owner)
    requests: list[dict[str, object]] = []
    for index, window in enumerate(repository.session(session_id, owner)["completed_windows"]):
        window_start, window_end = (
            datetime.fromisoformat(window["window_start"]),
            datetime.fromisoformat(window["window_end"]),
        )
        window_id = UUID(window["window_id"])
        repository.add_activity(BehavioralActivityEvent(
            session_id=session_id, event_time=window_end, ingested_at=window_end,
            idempotency_key=f"fixture-behavior-{index}", window_id=window_id,
            window_start=window_start, window_end=window_end, feature_cutoff=window_end,
            active_seconds=200 - index * 20, idle_seconds=100 + index * 20,
            keyboard_event_count=20 + index, pointer_event_count=10 + index,
            application_switch_count=index, build_count=None, test_count=index,
            source="synthetic_fixture", producer_version="1.0.0",
        ), owner)
        cv_available = index == 1
        if cv_available:
            repository.add_cv(CvFeatureWindowEvent(
                session_id=session_id, event_time=window_end, ingested_at=window_end,
                idempotency_key="fixture-cv-1", window_id=window_id,
                window_start=window_start, window_end=window_end, feature_cutoff=window_end,
                camera_available=True, face_presence_ratio=.9, gaze_away_ratio=.1,
                blink_rate_per_minute=12, head_pose_variance=.2, frames_sampled=100,
                frames_processed=99, frames_dropped=1, agent_version="1.0.0",
                asset_name="fixture", asset_sha256="f" * 64, cpu_seconds=1,
                latency_p50_ms=2, latency_p95_ms=3,
                source="synthetic_fixture", producer_version="1.0.0",
            ), owner)
        requests.append({
            "schema_version": "1.0", "session_id": session_id,
            "window_id": str(window_id), "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(), "feature_cutoff": window_end.isoformat(),
            "behavioral_contract_version": "1.0",
            "cv_contract_version": "1.0" if cv_available else None,
            "cv_available": cv_available, "label_window_ids_used": [],
        })
    args.requests.parent.mkdir(parents=True, exist_ok=True)
    args.requests.write_text(json.dumps(requests, sort_keys=True) + "\n")
    print(json.dumps({"session_id": session_id, "request_count": len(requests)}))


if __name__ == "__main__":
    main()
