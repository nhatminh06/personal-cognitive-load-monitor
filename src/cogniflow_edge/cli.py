"""Explicitly launched CV edge collector command."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from cogniflow_contracts import CvFeatureWindowEvent

from .asset import ASSET_NAME, ASSET_SHA256, verify_asset
from .features import FrameObservation, WindowQualityError, aggregate_window, window_diagnostics
from .mediapipe_backend import FaceLandmarkerProcessor, OpenCVCamera
from .runtime import CaptureLoop

logger = logging.getLogger("cogniflow_edge")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Local, aggregate-only CogniFlow CV collector")
    result.add_argument("--consent-camera", action="store_true", help="explicitly enable camera")
    result.add_argument("--model-asset", required=True, help="reviewed Face Landmarker .task path")
    result.add_argument("--camera-index", type=int, default=0)
    result.add_argument("--session-id", required=True)
    result.add_argument("--api-url", default="http://127.0.0.1:8000")
    result.add_argument(
        "--api-key", default=os.getenv("COGNIFLOW_EDGE_API_KEY") or os.getenv("COGNIFLOW_API_KEY"),
        help="API key (prefer COGNIFLOW_EDGE_API_KEY to avoid process arguments)",
    )
    return result


def _request(method: str, url: str, key: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=body, method=method,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"CogniFlow API is unavailable: {exc.reason}") from exc


def _next_window(session: dict, now: datetime) -> tuple[datetime, datetime]:
    if session["state"] not in {"session.started", "session.resumed"}:
        raise RuntimeError("Selected session is not actively collecting")
    segment_start = datetime.fromisoformat(session["last_event_time"])
    completed = max(0, math.ceil((now - segment_start).total_seconds() / 300))
    start = segment_start + timedelta(minutes=5 * completed)
    return start, start + timedelta(minutes=5)


def _run(args: argparse.Namespace) -> int:
    if not args.consent_camera:
        parser().error("--consent-camera is required; camera access is disabled by default")
    if not args.api_key:
        parser().error("set COGNIFLOW_EDGE_API_KEY or pass --api-key")
    asset = verify_asset(args.model_asset)
    base_url = args.api_url.rstrip("/")
    session_url = f"{base_url}/sessions/{args.session_id}"
    start, end = _next_window(_request("GET", session_url, args.api_key), datetime.now(UTC))
    delay = (start - datetime.now(UTC)).total_seconds()
    if delay > 0:
        time.sleep(delay)
    state = _request("GET", session_url, args.api_key)
    if state["state"] not in {"session.started", "session.resumed"}:
        raise RuntimeError("Session ended before the next complete window began")
    processor = FaceLandmarkerProcessor(asset)
    try:
        camera = OpenCVCamera(args.camera_index)
    except BaseException:
        logger.warning("camera_open_failed camera_index=%d", args.camera_index)
        processor.close()
        raise
    logger.info("camera_opened camera_index=%d", args.camera_index)
    loop = CaptureLoop(camera, processor, consent=True)
    observations: list[FrameObservation] = []
    cpu_start = time.process_time()
    last_state_check = time.monotonic()
    last_progress = last_state_check

    def accept(observation: FrameObservation) -> None:
        nonlocal last_progress, last_state_check
        observations.append(observation)
        now = time.monotonic()
        if now - last_progress >= 30:
            last_progress = now
            diagnostic = window_diagnostics(observations)
            progress = min(1.0, max(0.0, (datetime.now(UTC) - start) / (end - start)))
            logger.info(
                "window_progress progress=%.1f%% captured=%d processed=%d dropped=%d "
                "tracked=%d effective_fps=%.2f tracking_quality=%.1f%%",
                progress * 100, loop.frames_captured, loop.frames_processed,
                loop.frames_dropped, diagnostic["tracked_frames"],
                diagnostic["effective_fps"], float(diagnostic["tracking_quality"]) * 100,
            )
        if now - last_state_check >= 2:
            last_state_check = now
            if _request("GET", session_url, args.api_key)["state"] not in {
                "session.started", "session.resumed"
            } and datetime.now(UTC) < end:
                loop.stop()
        if datetime.now(UTC) >= end:
            loop.stop()

    try:
        loop.run(accept)
    finally:
        logger.info(
            "camera_closed captured=%d processed=%d dropped=%d",
            loop.frames_captured, loop.frames_processed, loop.frames_dropped,
        )
    if not observations:
        raise WindowQualityError(
            "no_frames", "No camera frames were processed", window_diagnostics(observations)
        )
    if datetime.now(UTC) < end:
        raise RuntimeError("Camera stopped before a complete window was observed")
    features = aggregate_window(observations, start, end)
    window_id = uuid5(NAMESPACE_URL, f"cogniflow:{args.session_id}:{start.isoformat()}:{end.isoformat()}")
    event = CvFeatureWindowEvent(
        event_id=uuid4(), session_id=args.session_id, event_time=end, ingested_at=datetime.now(UTC),
        source="local_cv_agent", producer_version="1.0.0",
        idempotency_key=f"{args.session_id}:cv:{window_id}", window_id=window_id,
        window_start=start, window_end=end, feature_cutoff=end, camera_available=True,
        frames_sampled=loop.frames_captured, frames_processed=loop.frames_processed,
        frames_dropped=loop.frames_dropped, agent_version="1.0.0",
        asset_name=ASSET_NAME, asset_sha256=ASSET_SHA256,
        cpu_seconds=time.process_time() - cpu_start, **features,
    )
    _request("POST", f"{session_url}/cv-windows", args.api_key, event.model_dump(mode="json"))
    diagnostic = window_diagnostics(observations)
    logger.info(
        "window_submitted tracked=%d effective_fps=%.2f tracking_quality=%.1f%%",
        diagnostic["tracked_frames"], diagnostic["effective_fps"],
        float(diagnostic["tracking_quality"]) * 100,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        return _run(parser().parse_args(argv))
    except KeyboardInterrupt:
        logger.info("collector_stopped reason=user_interrupt")
        return 130
    except WindowQualityError as exc:
        fields = " ".join(f"{key}={value:.3f}" if isinstance(value, float)
                          else f"{key}={value}" for key, value in exc.diagnostics.items())
        logger.warning("window_rejected reason=%s %s message=%s", exc.code, fields, exc)
        return 2
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        logger.warning("collector_unavailable reason=%s message=%s", type(exc).__name__, exc)
        return 2
