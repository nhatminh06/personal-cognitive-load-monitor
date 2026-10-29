"""Optional OpenCV and MediaPipe adapters, imported only by the edge CLI."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .features import FrameObservation


class OpenCVCamera:
    def __init__(self, index: int = 0):
        import cv2

        self._capture = cv2.VideoCapture(index)
        if not self._capture.isOpened():
            self._capture.release()
            raise RuntimeError(f"Camera {index} is unavailable")

    def read(self):
        return self._capture.read()

    def release(self) -> None:
        self._capture.release()


class FaceLandmarkerProcessor:
    def __init__(self, asset: Path):
        import mediapipe as mp

        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(asset)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._mp = mp
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

    def process(self, frame: Any, monotonic_ms: int) -> FrameObservation:
        import cv2

        started = time.perf_counter()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, monotonic_ms)
        latency = (time.perf_counter() - started) * 1000
        if not result.face_landmarks:
            return FrameObservation(monotonic_ms, False, None, None, None, latency)
        scores = {item.category_name: item.score for item in result.face_blendshapes[0]}
        eyes_closed = min(scores.get("eyeBlinkLeft", 0), scores.get("eyeBlinkRight", 0)) >= 0.55
        gaze_away = max(scores.get("eyeLookOutLeft", 0), scores.get("eyeLookOutRight", 0),
                        scores.get("eyeLookUpLeft", 0), scores.get("eyeLookUpRight", 0),
                        scores.get("eyeLookDownLeft", 0), scores.get("eyeLookDownRight", 0)) >= 0.5
        matrix = result.facial_transformation_matrixes[0]
        # Rotation displacement is a proxy, not a calibrated anatomical head pose.
        head_pose = sum(abs(float(matrix[row][column])) for row, column in ((0, 1), (0, 2), (1, 2)))
        return FrameObservation(monotonic_ms, True, gaze_away, eyes_closed, head_pose, latency)

    def close(self) -> None:
        self._landmarker.close()
