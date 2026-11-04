"""Hand-gesture recognition from MediaPipe hand landmarks.

A gesture is a *pose class*, and pose classes are cheap to read off 21
landmarks: which fingertips sit above their knuckles decides which fingers are
extended, and the combinations of extended fingers decide the name.  No second
model is needed beyond the HandLandmarker that produces the landmarks.

One ordering detail is worth stating because it is easy to get wrong: the
thumb is the only finger whose "extended" test is not a y-comparison
(it points sideways), so thumb-led poses have to be tested *before* the
all-fingers-curled case -- otherwise "thumbs up" is reported as a closed fist
and that branch is unreachable dead code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .models import model_path

__all__ = [
    "GestureType",
    "HandGesture",
    "GestureDetection",
    "GestureRecognizer",
]

log = logging.getLogger(__name__)

# Reported in place of a detector name when there is nothing to report.
STATE_DISABLED = "disabled"
STATE_UNAVAILABLE = "unavailable"
STATE_ERROR = "error"
STATE_NO_HANDS = "no-hands"
STATE_RUNNING = "mediapipe"

# Landmark indices from the MediaPipe hand topology.
WRIST = 0
THUMB_IP, THUMB_TIP = 3, 4
INDEX_MCP, INDEX_TIP = 5, 8
MIDDLE_MCP, MIDDLE_TIP = 9, 12
RING_MCP, RING_TIP = 13, 16
PINKY_MCP, PINKY_TIP = 17, 20

THUMB_SIDEWAYS_MARGIN = 0.02
OK_SIGN_MAX_GAP = 0.05


class GestureType(str, Enum):
    """Recognised gesture types."""

    OPEN_PALM = "open_palm"
    CLOSED_FIST = "closed_fist"
    POINTING = "pointing"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    PEACE = "peace_sign"
    OK_SIGN = "ok_sign"
    UNKNOWN = "unknown"


@dataclass
class HandGesture:
    """One detected hand gesture."""

    gesture: GestureType
    confidence: float
    hand_label: str  # "Left" or "Right"
    bbox: Tuple[int, int, int, int]
    landmarks: Optional[List[Tuple[float, float]]] = None

    def snapshot(self) -> dict:
        x, y, w, h = self.bbox
        return {
            "gesture": self.gesture.value,
            "confidence": round(self.confidence, 3),
            "hand": self.hand_label,
            "bbox": [int(x), int(y), int(w), int(h)],
        }


@dataclass
class GestureDetection:
    """Collection of detected gestures in one picture."""

    gestures: List[HandGesture] = field(default_factory=list)
    detector_name: str = STATE_DISABLED

    @property
    def count(self) -> int:
        return len(self.gestures)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "gestures": [gesture.snapshot() for gesture in self.gestures],
            "detector": self.detector_name,
        }


class GestureRecognizer:
    """Classify hand gestures with a MediaPipe HandLandmarker."""

    _model_file = "hand_landmarker.task"

    def __init__(
        self,
        max_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self.max_hands = max_hands
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self._hands = None
        self._failure: str | None = None

    @property
    def available(self) -> bool:
        return self._load_model() is not None

    @property
    def unavailable_reason(self) -> str | None:
        """Why the model is not loaded, for the API and the logs."""
        if self._failure is None and self._hands is None:
            self._load_model()
        return self._failure

    def _load_model(self):
        if self._hands is not None:
            return self._hands
        if self._failure is not None:
            return None

        try:
            from mediapipe.tasks import python as mp_tasks
            from mediapipe.tasks.python import vision as mp_vision

            options = mp_vision.HandLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(
                    model_asset_path=str(model_path(self._model_file))
                ),
                num_hands=self.max_hands,
                min_hand_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
                running_mode=mp_vision.RunningMode.IMAGE,
            )
            self._hands = mp_vision.HandLandmarker.create_from_options(options)
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            self._failure = f"{type(exc).__name__}: {exc}"
            log.info("GestureRecognizer unavailable: %s", self._failure)
        return self._hands

    def detect(self, frame: np.ndarray) -> GestureDetection:
        """Detect and classify hands in an RGB frame."""
        if self._load_model() is None:
            return GestureDetection([], STATE_UNAVAILABLE)

        try:
            import cv2
            import mediapipe as mp

            if frame.ndim == 2:
                rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            else:
                rgb = np.ascontiguousarray(frame)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self._hands.detect(image)
        except Exception as exc:  # noqa: BLE001 - a bad frame must not stop the stream
            log.warning("gesture detection failed: %s", exc)
            return GestureDetection([], STATE_ERROR)

        if not result.hand_landmarks:
            return GestureDetection([], STATE_NO_HANDS)

        height, width = frame.shape[:2]
        gestures = []
        for index, hand_landmarks in enumerate(result.hand_landmarks):
            label = "Unknown"
            if result.handedness and index < len(result.handedness):
                label = result.handedness[index][0].category_name
            gestures.append(
                HandGesture(
                    gesture=self._classify_gesture(hand_landmarks),
                    confidence=self._confidence_for(hand_landmarks),
                    hand_label=label,
                    bbox=self._bbox(hand_landmarks, width, height),
                    landmarks=[(lm.x, lm.y) for lm in hand_landmarks],
                )
            )
        return GestureDetection(gestures, STATE_RUNNING)

    @staticmethod
    def _bbox(hand_landmarks, width: int, height: int) -> Tuple[int, int, int, int]:
        xs = [lm.x * width for lm in hand_landmarks]
        ys = [lm.y * height for lm in hand_landmarks]
        x_min, x_max = int(min(xs)), int(max(xs))
        y_min, y_max = int(min(ys)), int(max(ys))
        return (x_min, y_min, x_max - x_min, y_max - y_min)

    @staticmethod
    def _extended_fingers(hand_landmarks) -> dict[str, bool]:
        """Which fingers are extended, judged by fingertip vs knuckle.

        The thumb is compared sideways because it folds across the palm rather
        than downwards, and on a mirrored image (a selfie camera) that sideways
        comparison reverses -- which is why the thumb result is reported
        separately and only used for poses that do not need its direction.
        """
        return {
            "thumb": hand_landmarks[THUMB_TIP].x < hand_landmarks[THUMB_IP].x - THUMB_SIDEWAYS_MARGIN,
            "index": hand_landmarks[INDEX_TIP].y < hand_landmarks[INDEX_MCP].y,
            "middle": hand_landmarks[MIDDLE_TIP].y < hand_landmarks[MIDDLE_MCP].y,
            "ring": hand_landmarks[RING_TIP].y < hand_landmarks[RING_MCP].y,
            "pinky": hand_landmarks[PINKY_TIP].y < hand_landmarks[PINKY_MCP].y,
        }

    def _classify_gesture(self, hand_landmarks: Sequence) -> GestureType:
        """Name the pose from the extended-finger pattern."""
        extended = self._extended_fingers(hand_landmarks)
        long_fingers = ["index", "middle", "ring", "pinky"]
        raised = sum(extended[finger] for finger in long_fingers)

        thumb_tip = hand_landmarks[THUMB_TIP]
        index_tip = hand_landmarks[INDEX_TIP]
        gap = float(np.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y))

        # OK: thumb and index tips touch while the other three stand up.
        if gap < OK_SIGN_MAX_GAP and raised >= 2 and extended["middle"] and extended["ring"]:
            return GestureType.OK_SIGN

        # Open palm: everything up, thumb included.
        if raised == 4 and extended["thumb"]:
            return GestureType.OPEN_PALM

        # Peace: index and middle only.
        if raised == 2 and extended["index"] and extended["middle"]:
            return GestureType.PEACE

        # Pointing: index only.
        if raised == 1 and extended["index"]:
            return GestureType.POINTING

        # Thumb poses must be tested before the fist: a raised thumb is also
        # "no long finger extended", which is exactly the fist's test.
        if raised == 0 and extended["thumb"]:
            if thumb_tip.y < hand_landmarks[WRIST].y:
                return GestureType.THUMBS_UP
            return GestureType.THUMBS_DOWN

        if raised == 0:
            return GestureType.CLOSED_FIST

        return GestureType.UNKNOWN

    @staticmethod
    def _confidence_for(hand_landmarks) -> float:
        """Confidence attached to a classified pose.

        These are fixed per pose rather than measured: the landmarker reports
        detection confidence, not classification confidence, and inventing a
        precise number for a rule-based classifier would overstate it.
        """
        return 0.8

    def reset(self) -> None:
        """Release the underlying landmarker so the next call reloads it."""
        if self._hands is not None:
            try:
                self._hands.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass
        self._hands = None
        self._failure = None
