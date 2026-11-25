"""Hand-gesture recognition from MediaPipe hand landmarks.

A gesture is a *pose class*, and pose classes are cheap to read off 21
landmarks: which fingertips sit above their knuckles decides which fingers are
extended, and the combinations of extended fingers decide the name.  No second
model is needed beyond the HandLandmarker that produces the landmarks.

Two details are worth stating because they are easy to get wrong.

The thumb is the only finger whose "extended" test is not a y-comparison: it
folds across the palm, so it is judged by how far its tip reaches from the
wrist compared with its own joint.  A sideways (handedness-dependent)
comparison reads a vertical thumbs-up as a fist, on a mirrored camera it
inverts, and it is exactly the pose the feature exists to recognise.

Thumb-led poses must then be tested *before* the all-fingers-curled case,
because "no long finger extended" is true for a thumbs-up as well -- order it
first and the fist rule swallows the gesture, leaving the thumb branches
unreachable dead code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence, Tuple

import numpy as np

from .models import model_path
from .states import (
    STATE_DISABLED,
    STATE_ERROR,
    STATE_NO_HANDS,
    STATE_RUNNING,
    STATE_UNAVAILABLE,
)

__all__ = [
    "GestureType",
    "HandGesture",
    "GestureDetection",
    "GestureRecognizer",
]

log = logging.getLogger(__name__)

# Landmark indices from the MediaPipe hand topology.
WRIST = 0
THUMB_IP, THUMB_TIP = 3, 4
INDEX_MCP, INDEX_TIP = 5, 8
MIDDLE_MCP, MIDDLE_TIP = 9, 12
RING_MCP, RING_TIP = 13, 16
PINKY_MCP, PINKY_TIP = 17, 20

#: Knuckle and tip index per long finger, in the order the rule table reads them.
FINGER_JOINTS = {
    "index": (INDEX_MCP, INDEX_TIP),
    "middle": (MIDDLE_MCP, MIDDLE_TIP),
    "ring": (RING_MCP, RING_TIP),
    "pinky": (PINKY_MCP, PINKY_TIP),
}

THUMB_REACH_RATIO = 1.15
#: A long finger counts as extended when its tip lies at least this far past its
#: knuckle along the palm axis, measured in palm lengths (wrist -> middle
#: knuckle).  A straight finger reaches roughly 0.8; a curled one folds back to
#: zero or below, so the gap between the two classes is wide.
FINGER_FORWARD_RATIO = 0.25
#: Thumb tip to index tip, in palm lengths, below which the two are touching.
OK_SIGN_MAX_GAP = 0.25


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
    state: str = STATE_DISABLED

    @property
    def count(self) -> int:
        return len(self.gestures)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "gestures": [gesture.snapshot() for gesture in self.gestures],
            "state": self.state,
        }


class GestureRecognizer:
    """Classify hand gestures with a MediaPipe HandLandmarker."""

    _model_file = "hand_landmarker.task"

    #: Per-pose confidence.  Fixed values, not measurements: the landmarker
    #: reports detection confidence, not classification confidence, so a
    #: made-up precise number would overstate what the rule table knows.  An
    #: unrecognised pose must not look as confident as a named one.
    CONFIDENCE = {
        GestureType.OPEN_PALM: 0.9,
        GestureType.CLOSED_FIST: 0.9,
        GestureType.POINTING: 0.85,
        GestureType.PEACE: 0.85,
        GestureType.THUMBS_UP: 0.8,
        GestureType.THUMBS_DOWN: 0.8,
        GestureType.OK_SIGN: 0.75,
        GestureType.UNKNOWN: 0.5,
    }

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
            gesture = self._classify_gesture(hand_landmarks)
            gestures.append(
                HandGesture(
                    gesture=gesture,
                    confidence=self.CONFIDENCE[gesture],
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
        """Which fingers are extended.

        The four long fingers are read as "fingertip above its knuckle".  The
        thumb folds *across* the palm instead of down, so its test is reach:
        an extended thumb's tip is farther from the wrist than its own
        interphalangeal joint, a folded one tucks back toward the palm.  A
        sideways comparison would read a vertical thumbs-up as a fist, and on a
        mirrored camera it would invert.

        The long fingers are judged **in the palm's own frame**, not in image
        coordinates.  Comparing ``tip.y`` with ``knuckle.y`` silently assumes
        the hand is upright: hold the same fist rotated 90 degrees — which is
        what a thumbs-up is — and the curled fingertips land above their
        knuckles, so every finger reads extended and the pose comes back as an
        open palm.  The palm axis (wrist to middle knuckle) is invariant under
        rotation and aspect ratio, so the test is too.  Measured in palm
        lengths, not pixels, so distance from the camera does not matter.

        Known limit, stated rather than hidden: a fist with the thumb tucked
        flat across the knuckles also passes the thumb test and reads as
        ``thumbs_up``.  Distinguishing the two needs palm-relative geometry
        (where the tip lies relative to the four knuckles), which is the next
        step if the pose matters; see ``docs/FEATURES.md``.
        """
        wrist = hand_landmarks[WRIST]
        thumb_tip = hand_landmarks[THUMB_TIP]
        thumb_joint = hand_landmarks[THUMB_IP]
        reach = np.hypot(thumb_tip.x - wrist.x, thumb_tip.y - wrist.y)
        folded_reach = np.hypot(thumb_joint.x - wrist.x, thumb_joint.y - wrist.y)

        extended = {"thumb": reach > folded_reach * THUMB_REACH_RATIO}

        palm = hand_landmarks[MIDDLE_MCP]
        axis_x = palm.x - wrist.x
        axis_y = palm.y - wrist.y
        palm_length = float(np.hypot(axis_x, axis_y))
        if palm_length < 1e-9:
            # Degenerate landmarks cannot define a frame; fall back to the
            # upright assumption rather than dividing by zero.
            for name, (mcp, tip) in FINGER_JOINTS.items():
                extended[name] = hand_landmarks[tip].y < hand_landmarks[mcp].y
            return extended

        unit_x, unit_y = axis_x / palm_length, axis_y / palm_length
        for name, (mcp, tip) in FINGER_JOINTS.items():
            dx = hand_landmarks[tip].x - hand_landmarks[mcp].x
            dy = hand_landmarks[tip].y - hand_landmarks[mcp].y
            forward = (dx * unit_x + dy * unit_y) / palm_length
            extended[name] = forward > FINGER_FORWARD_RATIO
        return extended

    @staticmethod
    def _palm_length(hand_landmarks: Sequence) -> float:
        """Wrist-to-middle-knuckle distance; the hand's own unit of length."""
        wrist = hand_landmarks[WRIST]
        palm = hand_landmarks[MIDDLE_MCP]
        length = float(np.hypot(palm.x - wrist.x, palm.y - wrist.y))
        return length if length > 1e-9 else 1.0

    def _classify_gesture(self, hand_landmarks: Sequence) -> GestureType:
        """Name the pose from the extended-finger pattern."""
        extended = self._extended_fingers(hand_landmarks)
        long_fingers = ["index", "middle", "ring", "pinky"]
        raised = sum(extended[finger] for finger in long_fingers)

        thumb_tip = hand_landmarks[THUMB_TIP]
        index_tip = hand_landmarks[INDEX_TIP]
        gap = float(np.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y))
        # The same gap means different things on a near hand and a far one, so
        # the threshold is a fraction of the palm, not a slice of the frame.
        gap_in_palms = gap / self._palm_length(hand_landmarks)

        # OK: thumb and index tips touch while the other three stand up.
        if (
            gap_in_palms < OK_SIGN_MAX_GAP
            and raised >= 2
            and extended["middle"]
            and extended["ring"]
        ):
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

    def close(self) -> None:
        """Release the landmarker and stop reporting availability."""
        hands, self._hands = self._hands, None
        self._failure = "closed"
        if hands is not None:
            try:
                hands.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass
