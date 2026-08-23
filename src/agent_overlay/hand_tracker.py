"""Watches the webcam and emits one HandFrame per frame via Qt signals, on a background
thread so the ~30fps capture-and-inference loop never blocks the UI. Hand landmark
detection is delegated to Google's MediaPipe Hands, which ships its own pretrained
model -- no separate model file to source, just `pip install mediapipe opencv-python`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import cv2

# Imported as a direct submodule rather than accessed as mp.solutions.hands: on some
# MediaPipe packaging/versions (observed on Windows), the top-level `mediapipe` module
# doesn't expose `.solutions` as an attribute even though the underlying code is present,
# raising AttributeError("module 'mediapipe' has no attribute 'solutions'") at the call
# site. Importing the submodule directly routes around whatever's failing in that
# top-level exposure.
from mediapipe.python.solutions import hands as mp_hands
from PySide6.QtCore import QThread, Signal


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
        # The whole body is wrapped, not just the frame loop: an exception from
        # constructing VideoCapture/Hands is just as fatal to this thread as one from the
        # loop, and letting it escape uncaught here doesn't get caught by Python at all --
        # it crosses back into Qt/Shiboken's C++ call boundary, which can only report it
        # as an opaque "Error calling Python override of QThread::run()" with no detail.
        capture = None
        hands = None
        try:
            capture = cv2.VideoCapture(self._camera_index)
            if not capture.isOpened():
                self.failed.emit(f"Could not open camera index {self._camera_index}.")
                return

            hands = mp_hands.Hands(
                model_complexity=0,
                max_num_hands=1,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5,
            )

            while not self.isInterruptionRequested():
                ok, frame = capture.read()
                if not ok:
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(frame_rgb)

                if result.multi_hand_landmarks:
                    landmarks = result.multi_hand_landmarks[0].landmark
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
            if hands is not None:
                hands.close()
            if capture is not None:
                capture.release()

    def stop(self) -> None:
        self.requestInterruption()
        self.wait(2000)
