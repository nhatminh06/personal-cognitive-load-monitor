"""Bounded capture loop with explicit consent and deterministic release."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from .features import FrameObservation


class Camera(Protocol):
    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...


class Processor(Protocol):
    def process(self, frame: Any, monotonic_ms: int) -> FrameObservation: ...
    def close(self) -> None: ...


class CaptureLoop:
    def __init__(self, camera: Camera, processor: Processor, *, consent: bool):
        if not consent:
            raise PermissionError("Camera capture requires --consent-camera")
        self.camera, self.processor = camera, processor
        self.frames_captured = self.frames_processed = self.frames_dropped = 0
        self._frames: queue.Queue[tuple[Any, int] | None] = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._error: BaseException | None = None
        self._last_timestamp = -1

    def run(self, accept: Callable[[FrameObservation], None]) -> None:
        worker = threading.Thread(target=self._process, args=(accept,), daemon=True)
        worker.start()
        try:
            while not self._stop.is_set():
                ok, frame = self.camera.read()
                if not ok:
                    break
                self.frames_captured += 1
                timestamp = max(time.monotonic_ns() // 1_000_000, self._last_timestamp + 1)
                self._last_timestamp = timestamp
                item = (frame, timestamp)
                try:
                    self._frames.put_nowait(item)
                except queue.Full:
                    self.frames_dropped += 1
        finally:
            self._stop.set()
            try:
                self._frames.put(None, timeout=1)
            except queue.Full:
                pass
            worker.join(timeout=5)
            self.frames_dropped = self.frames_captured - self.frames_processed
            self.camera.release()
            self.processor.close()
        if self._error is not None:
            raise self._error

    def stop(self) -> None:
        self._stop.set()

    def _process(self, accept: Callable[[FrameObservation], None]) -> None:
        while True:
            try:
                item = self._frames.get(timeout=0.1)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            if item is None:
                return
            frame, timestamp = item
            try:
                accept(self.processor.process(frame, timestamp))
                self.frames_processed += 1
            except BaseException as exc:
                self._error = exc
                self._stop.set()
                return
