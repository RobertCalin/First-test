"""Reads the webcam, runs MediaPipe Hands, and prints one JSON object per frame to
stdout describing the detected gesture and the index fingertip's normalized position.

Launched as a child process by PythonHandTracker.cs -- not meant to be run standalone,
though `python hand_tracker.py` works fine for manual testing (Ctrl+C to stop).

Requires: pip install -r requirements.txt
"""

import argparse
import json
import sys
import time

import cv2
import mediapipe as mp


def _distance(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def _finger_extended(landmarks, tip_index: int, pip_index: int) -> bool:
    # A finger pointing "up" toward the camera has its tip at a smaller normalized y
    # than its middle (PIP) joint. This is a simple heuristic, not a robust classifier --
    # it assumes the hand is roughly upright and facing the camera.
    return landmarks[tip_index].y < landmarks[pip_index].y


def classify_gesture(landmarks) -> str:
    wrist = landmarks[0]
    middle_mcp = landmarks[9]
    scale = _distance(wrist, middle_mcp) or 1e-6

    pinch_distance = _distance(landmarks[4], landmarks[8]) / scale
    if pinch_distance < 0.4:
        return "pinch"

    index_ext = _finger_extended(landmarks, 8, 6)
    middle_ext = _finger_extended(landmarks, 12, 10)
    ring_ext = _finger_extended(landmarks, 16, 14)
    pinky_ext = _finger_extended(landmarks, 20, 18)

    if index_ext and not (middle_ext or ring_ext or pinky_ext):
        return "point"
    if not (index_ext or middle_ext or ring_ext or pinky_ext):
        return "fist"
    if index_ext and middle_ext and ring_ext and pinky_ext:
        return "open_palm"
    return "none"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    args = parser.parse_args()

    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        print(json.dumps({"error": f"could not open camera index {args.camera}"}), flush=True)
        sys.exit(1)

    hands = mp.solutions.hands.Hands(
        model_complexity=0,
        max_num_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.5,
    )

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(frame_rgb)

            payload = {
                "hand_present": False,
                "gesture": "none",
                "cursor_x": 0.0,
                "cursor_y": 0.0,
                "ts": time.time(),
            }

            if result.multi_hand_landmarks:
                landmarks = result.multi_hand_landmarks[0].landmark
                index_tip = landmarks[8]
                payload["hand_present"] = True
                payload["gesture"] = classify_gesture(landmarks)
                payload["cursor_x"] = index_tip.x
                payload["cursor_y"] = index_tip.y

            print(json.dumps(payload), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        hands.close()
        capture.release()


if __name__ == "__main__":
    main()
