"""Privacy, aggregation, bounded runtime, and CV ingestion tests."""

from __future__ import annotations

import hashlib
import asyncio
import sys
import threading
import time
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import httpx

from cogniflow_contracts import CvFeatureWindowEvent, SessionLifecycleEvent
from cogniflow_edge.asset import verify_asset
import cogniflow_edge.cli as edge_cli
from cogniflow_edge.cli import main
from cogniflow_edge.features import FrameObservation, WindowQualityError, aggregate_window
from cogniflow_edge.mediapipe_backend import OpenCVCamera
from cogniflow_edge.runtime import CaptureLoop
from cogniflow_sessions import ConflictError, FocusSessionRepository
from preprocessing_api.main import app
from preprocessing_api.sessions import get_session_repository

OWNER = hashlib.sha256(b"secret").hexdigest()
START = datetime.now(UTC) - timedelta(minutes=6)


def lifecycle(kind: str, sequence: int, when: datetime) -> SessionLifecycleEvent:
    return SessionLifecycleEvent(
        session_id="cv-1", event_time=when, ingested_at=when + timedelta(seconds=1),
        source="local_api", producer_version="1.0.0", idempotency_key=f"cv-1:{sequence}",
        event_type=f"session.{kind}", sequence=sequence, session_kind="programming",
        privacy_mode="behavioral",
    )


def observations(count: int = 3001) -> list[FrameObservation]:
    return [FrameObservation(
        monotonic_ms=index * 100, tracked=index % 20 != 0,
        gaze_away=index % 10 == 0, eyes_closed=index % 100 in {0, 1},
        head_pose_degrees=float(index % 5), latency_ms=float(10 + index % 3),
    ) for index in range(count)]


def cv_event(window: dict, **changes) -> CvFeatureWindowEvent:
    payload = {
        "session_id": "cv-1", "event_time": window["window_end"],
        "ingested_at": datetime.now(UTC), "source": "local_cv_agent",
        "producer_version": "1.0.0", "idempotency_key": "cv-1:window:1",
        **window, "feature_cutoff": window["window_end"], "camera_available": True,
        "frames_sampled": 100, "frames_processed": 95, "frames_dropped": 5,
        "agent_version": "1.0.0", "asset_name": "face_landmarker",
        "asset_sha256": "a" * 64, "cpu_seconds": 2,
        "face_presence_ratio": 0.95, "gaze_away_ratio": 0.1,
        "blink_rate_per_minute": 12, "head_pose_variance": 0.3,
        "latency_p50_ms": 10, "latency_p95_ms": 15,
    }
    payload.update(changes)
    return CvFeatureWindowEvent.model_validate(payload)


def test_aggregation_is_bounded_and_rejects_weak_or_slow_tracking():
    end = START + timedelta(minutes=5)
    result = aggregate_window(observations(), START, end)
    assert result["face_presence_ratio"] == pytest.approx(0.94968, rel=1e-3)
    assert result["blink_rate_per_minute"] > 0
    with pytest.raises(WindowQualityError, match="No processed frame") as unavailable:
        aggregate_window([FrameObservation(i * 100, False, None, None, None, 1)
                          for i in range(3001)], START, end)
    assert unavailable.value.code == "tracking_unavailable"
    partial = [FrameObservation(i * 100, i % 5 != 0, False if i % 5 else None,
                                False if i % 5 else None, 0 if i % 5 else None, 1)
               for i in range(3001)]
    with pytest.raises(WindowQualityError, match="below the required 80%") as weak:
        aggregate_window(partial, START, end)
    assert weak.value.diagnostics["tracked_frames"] == 2400
    slow = [FrameObservation(i * 200, True, False, False, 0, 1) for i in range(10)]
    with pytest.raises(WindowQualityError, match="10 effective FPS") as blink:
        aggregate_window(slow, START, end)
    assert blink.value.code == "blink_sampling"
    with pytest.raises(WindowQualityError, match="No camera frames") as empty:
        aggregate_window([], START, end)
    assert empty.value.code == "no_frames"


def test_missing_asset_and_default_disabled_do_not_import_cv(monkeypatch, tmp_path):
    with pytest.raises(FileNotFoundError):
        verify_asset(tmp_path / "missing.task")
    monkeypatch.setattr(sys, "argv", ["cogniflow-edge", "--model-asset", "missing",
                                      "--session-id", "cv-1", "--api-key", "secret"])
    with pytest.raises(SystemExit):
        main()
    assert "cv2" not in sys.modules and "mediapipe" not in sys.modules


def test_api_key_prefers_private_environment_input(monkeypatch):
    monkeypatch.setenv("COGNIFLOW_EDGE_API_KEY", "environment-secret")
    args = edge_cli.parser().parse_args([
        "--consent-camera", "--model-asset", "asset", "--session-id", "cv-1",
    ])
    assert args.api_key == "environment-secret"


def test_bounded_capture_drops_and_releases():
    class Camera:
        released = False
        count = 0
        def read(self):
            self.count += 1
            return (self.count <= 100, object())
        def release(self):
            self.released = True

    class Processor:
        closed = False
        def process(self, frame, timestamp):
            time.sleep(0.001)
            return FrameObservation(timestamp, True, False, False, 0, 1)
        def close(self):
            self.closed = True

    camera, processor = Camera(), Processor()
    loop = CaptureLoop(camera, processor, consent=True)
    loop.run(lambda item: None)
    assert camera.released and processor.closed
    assert loop.frames_captured == loop.frames_processed + loop.frames_dropped
    assert loop.frames_dropped > 0
    with pytest.raises(PermissionError):
        CaptureLoop(camera, processor, consent=False)


def test_camera_unavailable_releases_handle(monkeypatch):
    class Capture:
        released = False
        def isOpened(self):
            return False
        def release(self):
            self.released = True

    capture = Capture()
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(VideoCapture=lambda index: capture))
    with pytest.raises(RuntimeError, match="Camera 3 is unavailable"):
        OpenCVCamera(3)
    assert capture.released


def test_processing_failure_stops_and_cleans_up():
    class Camera:
        released = False
        def read(self):
            return True, object()
        def release(self):
            self.released = True

    class Processor:
        closed = False
        def process(self, frame, timestamp):
            raise RuntimeError("tracking backend stopped")
        def close(self):
            self.closed = True

    camera, processor = Camera(), Processor()
    with pytest.raises(RuntimeError, match="tracking backend stopped"):
        CaptureLoop(camera, processor, consent=True).run(lambda item: None)
    assert camera.released and processor.closed


def test_expected_quality_failure_is_graceful(monkeypatch, caplog):
    error = WindowQualityError(
        "tracking_quality", "Face tracking was below the required 80%",
        {"processed_frames": 100, "tracked_frames": 25,
         "tracking_quality": 0.25, "effective_fps": 12.0},
    )
    monkeypatch.setattr(edge_cli, "_run", lambda args: (_ for _ in ()).throw(error))
    result = edge_cli.main(["--consent-camera", "--model-asset", "asset",
                            "--session-id", "cv-1", "--api-key", "secret"])
    assert result == 2
    assert "reason=tracking_quality" in caplog.text
    assert "tracked_frames=25" in caplog.text
    assert "Traceback" not in caplog.text


def test_cv_repository_live_window_idempotency_privacy_and_conflict(tmp_path):
    repository = FocusSessionRepository(tmp_path / "cv.sqlite3")
    repository.create(lifecycle("started", 1, START), OWNER)
    window = {
        "window_id": str(__import__("uuid").uuid5(
            __import__("uuid").NAMESPACE_URL,
            f"cogniflow:cv-1:{START.isoformat()}:{(START + timedelta(minutes=5)).isoformat()}",
        )),
        "window_start": START, "window_end": START + timedelta(minutes=5),
    }
    event = cv_event(window)
    assert repository.add_cv(event, OWNER)[1]
    assert not repository.add_cv(event, OWNER)[1]
    with pytest.raises(ConflictError, match="already has"):
        repository.add_cv(cv_event(window, event_id=uuid4(), idempotency_key="different"), OWNER)
    assert repository.timeline("cv-1", OWNER, 100, 0)["items"][-1]["event_type"] == "cv.window"
    data = repository.path.read_bytes()
    assert b"face_landmarks" not in data and b"raw_frame" not in data


def test_concurrent_cv_submissions_have_one_winner_and_survive_restart(tmp_path):
    path = tmp_path / "concurrent-cv.sqlite3"
    repository = FocusSessionRepository(path)
    repository.create(lifecycle("started", 1, START), OWNER)
    window_id = __import__("uuid").uuid5(
        __import__("uuid").NAMESPACE_URL,
        f"cogniflow:cv-1:{START.isoformat()}:{(START + timedelta(minutes=5)).isoformat()}",
    )
    window = {"window_id": window_id, "window_start": START,
              "window_end": START + timedelta(minutes=5)}
    events = [cv_event(window, event_id=uuid4(), idempotency_key=f"race:{index}",
                       gaze_away_ratio=index / 10) for index in range(2)]
    results: list[str] = []

    def submit(event):
        try:
            FocusSessionRepository(path).add_cv(event, OWNER)
            results.append("ok")
        except ConflictError:
            results.append("conflict")

    workers = [threading.Thread(target=submit, args=(event,)) for event in events]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert sorted(results) == ["conflict", "ok"]
    assert sum(item.get("event_type") == "cv.window" for item in
               FocusSessionRepository(path).timeline("cv-1", OWNER, 100, 0)["items"]) == 1


def test_cv_api_authentication_validation_and_idempotency(tmp_path, monkeypatch):
    monkeypatch.setenv("COGNIFLOW_API_KEY", "secret")
    repository = FocusSessionRepository(tmp_path / "api.sqlite3")
    repository.create(lifecycle("started", 1, START), OWNER)
    window_id = __import__("uuid").uuid5(
        __import__("uuid").NAMESPACE_URL,
        f"cogniflow:cv-1:{START.isoformat()}:{(START + timedelta(minutes=5)).isoformat()}",
    )
    event = cv_event({"window_id": window_id, "window_start": START,
                      "window_end": START + timedelta(minutes=5)})

    async def dependency():
        return repository

    async def send(headers=None, payload=None):
        app.dependency_overrides[get_session_repository] = dependency
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                return await client.post("/sessions/cv-1/cv-windows", headers=headers,
                                         json=payload or event.model_dump(mode="json"))
        finally:
            app.dependency_overrides.clear()

    assert asyncio.run(send()).status_code == 401
    assert asyncio.run(send({"x-api-key": "secret"})).status_code == 201
    assert asyncio.run(send({"x-api-key": "secret"})).status_code == 200
    private = {**event.model_dump(mode="json"), "raw_landmarks": [[0, 0, 0]]}
    assert asyncio.run(send({"x-api-key": "secret"}, private)).status_code == 422
