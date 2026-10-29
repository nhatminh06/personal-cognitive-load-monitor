"""Aggregate ephemeral frame observations without retaining frames or landmarks."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import cast


@dataclass(frozen=True, slots=True)
class FrameObservation:
    monotonic_ms: int
    tracked: bool
    gaze_away: bool | None
    eyes_closed: bool | None
    head_pose_degrees: float | None
    latency_ms: float


class WindowQualityError(ValueError):
    """An expected, privacy-safe reason that an aggregate cannot be emitted."""

    def __init__(self, code: str, message: str, diagnostics: dict[str, float | int]):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


def window_diagnostics(observations: list[FrameObservation]) -> dict[str, float | int]:
    tracked = sum(item.tracked for item in observations)
    timestamps = [item.monotonic_ms for item in observations]
    duration = (timestamps[-1] - timestamps[0]) / 1000 if len(timestamps) > 1 else 0
    return {
        "processed_frames": len(observations),
        "tracked_frames": tracked,
        "tracking_quality": tracked / len(observations) if observations else 0.0,
        "effective_fps": (len(observations) - 1) / duration if duration else 0.0,
    }


def aggregate_window(observations: list[FrameObservation], start: datetime, end: datetime) -> dict:
    """Return contract fields only when every metric is defensible."""
    if end <= start or (end - start).total_seconds() != 300:
        raise ValueError("CV aggregation requires one exact five-minute window")
    diagnostics = window_diagnostics(observations)
    if not observations:
        raise WindowQualityError("no_frames", "No camera frames were processed", diagnostics)
    timestamps = [item.monotonic_ms for item in observations]
    if timestamps != sorted(set(timestamps)):
        raise ValueError("Frame timestamps must be strictly increasing")
    tracked = [item for item in observations if item.tracked]
    if not tracked:
        raise WindowQualityError(
            "tracking_unavailable", "No processed frame contained a face track", diagnostics
        )
    if len(tracked) / len(observations) < 0.8:
        raise WindowQualityError(
            "tracking_quality", "Face tracking was below the required 80%", diagnostics
        )
    if any(item.gaze_away is None or item.eyes_closed is None or
           item.head_pose_degrees is None for item in tracked):
        raise WindowQualityError(
            "incomplete_tracking", "Tracked frames lacked required proxy values", diagnostics
        )
    effective_fps = float(diagnostics["effective_fps"])
    if effective_fps < 10:
        raise WindowQualityError(
            "blink_sampling", "Blink rate requires at least 10 effective FPS", diagnostics
        )
    blink_count = sum(
        not bool(previous.eyes_closed) and bool(current.eyes_closed)
        for previous, current in zip(tracked, tracked[1:])
    )
    latencies = [item.latency_ms for item in observations]
    ordered = sorted(latencies)
    p95 = ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]
    poses = [cast(float, item.head_pose_degrees) for item in tracked]
    return {
        "face_presence_ratio": len(tracked) / len(observations),
        "gaze_away_ratio": sum(bool(item.gaze_away) for item in tracked) / len(tracked),
        "blink_rate_per_minute": blink_count / 5,
        "head_pose_variance": statistics.pvariance(poses),
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": p95,
    }
