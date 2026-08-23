"""Watches the webcam and emits one HandFrame per frame via Qt signals, on a background
thread so the ~30fps capture-and-inference loop never blocks the UI. Hand landmark
detection is delegated to Google's MediaPipe Tasks HandLandmarker.

Unlike the older, now-removed "Solutions" API (mp.solutions.hands), Tasks does not bundle
its model inside the pip package -- it needs a separate .task model file. _ensure_model()
below downloads it once from Google's public model zoo and caches it locally, so this
still doesn't require the user to source or manage a model file by hand.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision
from PySide6.QtCore import QThread, Signal

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
_MODEL_PATH = Path(__file__).parent / "models" / "hand_landmarker.task"


class HandGesture(Enum):
    NONE = auto()
    POINT = auto()
    PINCH = auto()
    FIST = auto()
    OPEN_PALM = auto()


@dataclass(frozen=True)
class HandFrame:
    """cursor_x/y are the index fingertip's position in normalized camera-space
    coordinates (0..1), in the camera's native (unmirrored) left-right orientation --
    a caller mapping this to screen coordinates for a front-facing webcam should mirror
    x so "move your hand right" moves the cursor right."""

    hand_present: bool
    gesture: HandGesture
    cursor_x: float
    cursor_y: float


def _ensure_model() -> Path:
    """Downloads the hand landmark model to a local cache on first use. Runs on the
    tracker's background thread, so a slow/blocked download doesn't freeze the UI --
    it just delays hand control coming online, same as any other startup wait."""
    if _MODEL_PATH.exists():
        return _MODEL_PATH
    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
    return _MODEL_PATH


def _distance(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _finger_extended(landmarks, tip_index: int, pip_index: int) -> bool:
    # A finger pointing "up" toward the camera has its tip at a smaller normalized y
    # than its middle (PIP) joint. Simple heuristic, not a robust classifier -- assumes
    # the hand is roughly upright and facing the camera.
    return landmarks[tip_index].y < landmarks[pip_index].y


def _classify_gesture(landmarks) -> HandGesture:
    wrist = landmarks[0]
    middle_mcp = landmarks[9]
    scale = _distance(wrist, middle_mcp) or 1e-6

    if _distance(landmarks[4], landmarks[8]) / scale < 0.4:
        return HandGesture.PINCH

    index_ext = _finger_extended(landmarks, 8, 6)
    middle_ext = _finger_extended(landmarks, 12, 10)
    ring_ext = _finger_extended(landmarks, 16, 14)
    pinky_ext = _finger_extended(landmarks, 20, 18)

    if index_ext and not (middle_ext or ring_ext or pinky_ext):
        return HandGesture.POINT
    if not (index_ext or middle_ext or ring_ext or pinky_ext):
        return HandGesture.FIST
    if index_ext and middle_ext and ring_ext and pinky_ext:
        return HandGesture.OPEN_PALM
    return HandGesture.NONE


class HandTrackerThread(QThread):
    frame_received = Signal(object)  # HandFrame
    failed = Signal(str)

    def __init__(self, camera_index: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._camera_index = camera_index

    def run(self) -> None:
        # The whole body is wrapped, not just the frame loop: an exception from setup
        # (model download, VideoCapture, HandLandmarker) is just as fatal to this thread
        # as one from the loop, and letting it escape uncaught here doesn't get caught by
        # Python at all -- it crosses back into Qt/Shiboken's C++ call boundary, which can
        # only report it as an opaque "Error calling Python override of QThread::run()".
        capture = None
        landmarker = None
        try:
            try:
                model_path = _ensure_model()
            except Exception as exc:
                self.failed.emit(
                    f"Could not download hand-tracking model ({exc!r}). Download it "
                    f"manually from {_MODEL_URL} and save it to {_MODEL_PATH}."
                )
                return

            capture = cv2.VideoCapture(self._camera_index)
            if not capture.isOpened():
                self.failed.emit(f"Could not open camera index {self._camera_index}.")
                return

            options = mp_vision.HandLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
                running_mode=mp_vision.RunningMode.IMAGE,
                num_hands=1,
                min_hand_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )
            landmarker = mp_vision.HandLandmarker.create_from_options(options)

            while not self.isInterruptionRequested():
                ok, frame = capture.read()
                if not ok:
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                result = landmarker.detect(mp_image)

                if result.hand_landmarks:
                    landmarks = result.hand_landmarks[0]
                    index_tip = landmarks[8]
                    self.frame_received.emit(
                        HandFrame(
                            hand_present=True,
                            gesture=_classify_gesture(landmarks),
                            cursor_x=index_tip.x,
                            cursor_y=index_tip.y,
                        )
                    )
                else:
                    self.frame_received.emit(HandFrame(False, HandGesture.NONE, 0.0, 0.0))
        except Exception as exc:  # noqa: BLE001 -- must never die silently on this thread
            self.failed.emit(f"Hand tracker crashed: {exc!r}")
        finally:
            if landmarker is not None:
                landmarker.close()
            if capture is not None:
                capture.release()

    def stop(self) -> None:
        self.requestInterruption()
        self.wait(2000)
