"""Hand-gesture classification from synthetic landmarks.

The classifier is a rule table over 21 landmark coordinates, so it can be
tested exactly: build the landmark set a pose implies, and the expected name
must come back.  That is the only way to test the poses without a camera in
the room, and it is also what pins the thumb-vs-fist ordering -- a raised thumb
also satisfies "no long finger extended", so getting the order wrong turns
"thumbs up" into "closed fist" and leaves the thumb branches unreachable.
"""

from types import SimpleNamespace

import numpy as np

from rvm.analysis.gesture import (
    GestureDetection,
    GestureRecognizer,
    GestureType,
    HandGesture,
)

# MediaPipe hand topology: fingertip and knuckle index per long finger.
FINGERS = {
    "index": (5, 8),
    "middle": (9, 12),
    "ring": (13, 16),
    "pinky": (17, 20),
}
WRIST_Y = 0.9
THUMB_IP = (0.40, 0.80)


def make_hand(extended=(), thumb_extended=True, thumb_above_wrist=True, ok_gap=None):
    """Landmarks for a hand whose listed fingers are extended.

    Fingertips sit above their knuckles when a finger is extended (smaller y)
    and below when it is curled.  The thumb is folded sideways, which is why it
    needs its own argument.
    """
    points = {0: (0.5, WRIST_Y)}
    points[3] = THUMB_IP
    thumb_y = 0.70 if thumb_above_wrist else 0.95
    points[4] = (0.30, thumb_y) if thumb_extended else (0.60, 0.80)

    for position, (name, (mcp, tip)) in enumerate(FINGERS.items()):
        x = 0.42 + 0.04 * position
        points[mcp] = (x, 0.60)
        points[tip] = (x, 0.40) if name in extended else (x, 0.70)

    if ok_gap is not None:
        points[8] = (points[4][0] + ok_gap, points[4][1])

    # Only the wrist, thumb and the ten knuckle/tip joints are read by the
    # classifier; the rest of the 21 joints are filled so the landmark set has
    # the shape MediaPipe would hand over.
    return [
        SimpleNamespace(x=points.get(i, (0.5, 0.65))[0], y=points.get(i, (0.5, 0.65))[1])
        for i in range(21)
    ]


def classify(**kwargs):
    return GestureRecognizer()._classify_gesture(make_hand(**kwargs))


# --------------------------------------------------------------------------
# Each pose is named from the extended-finger pattern
# --------------------------------------------------------------------------


def test_open_palm_needs_all_four_long_fingers_and_the_thumb():
    assert classify(extended=tuple(FINGERS), thumb_extended=True) is GestureType.OPEN_PALM


def test_all_fingers_up_without_the_thumb_is_not_an_open_palm():
    assert classify(extended=tuple(FINGERS), thumb_extended=False) is not GestureType.OPEN_PALM


def test_closed_fist_when_nothing_is_extended():
    assert classify(extended=(), thumb_extended=False) is GestureType.CLOSED_FIST


def test_pointing_is_the_index_alone():
    assert classify(extended=("index",), thumb_extended=False) is GestureType.POINTING


def test_peace_sign_is_index_and_middle():
    assert classify(extended=("index", "middle"), thumb_extended=False) is GestureType.PEACE


def test_an_unrecognised_combination_is_reported_as_unknown():
    assert classify(extended=("index", "ring"), thumb_extended=False) is GestureType.UNKNOWN


# --------------------------------------------------------------------------
# Thumb-led poses: the ordering this module had to get right
# --------------------------------------------------------------------------


def test_a_raised_thumb_over_a_fist_is_thumbs_up_not_a_fist():
    assert classify(extended=(), thumb_extended=True, thumb_above_wrist=True) is GestureType.THUMBS_UP


def test_a_thumb_below_the_wrist_over_a_fist_is_thumbs_down():
    assert classify(extended=(), thumb_extended=True, thumb_above_wrist=False) is GestureType.THUMBS_DOWN


def test_ok_sign_is_thumb_and_index_touching_with_the_others_up():
    gesture = classify(extended=("middle", "ring"), thumb_extended=True, ok_gap=0.02)
    assert gesture is GestureType.OK_SIGN


def test_ok_sign_is_not_reported_when_the_tips_are_apart():
    gesture = classify(extended=("middle", "ring"), thumb_extended=True, ok_gap=0.20)
    assert gesture is not GestureType.OK_SIGN


# --------------------------------------------------------------------------
# Data shapes the dashboard and the API consume
# --------------------------------------------------------------------------


def test_hand_gesture_snapshot_uses_json_friendly_types():
    gesture = HandGesture(
        gesture=GestureType.POINTING,
        confidence=0.85,
        hand_label="Right",
        bbox=(10, 20, 30, 40),
    )
    assert gesture.snapshot() == {
        "gesture": "pointing",
        "confidence": 0.85,
        "hand": "Right",
        "bbox": [10, 20, 30, 40],
    }


def test_detection_snapshot_counts_what_it_holds():
    detection = GestureDetection(
        [
            HandGesture(GestureType.PEACE, 0.8, "Left", (1, 2, 3, 4)),
            HandGesture(GestureType.THUMBS_UP, 0.8, "Right", (5, 6, 7, 8)),
        ],
        "mediapipe",
    )
    snapshot = detection.snapshot()
    assert snapshot["count"] == 2
    assert snapshot["detector"] == "mediapipe"
    assert len(snapshot["gestures"]) == 2


def test_recognizer_settings_are_configurable():
    recognizer = GestureRecognizer(
        max_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.6
    )
    assert recognizer.max_hands == 1
    assert recognizer.min_detection_confidence == 0.7
    assert recognizer.min_tracking_confidence == 0.6


def test_detecting_on_a_blank_frame_reports_a_state_and_never_raises():
    detection = GestureRecognizer().detect(np.zeros((120, 160, 3), dtype=np.uint8))
    assert isinstance(detection, GestureDetection)
    assert detection.detector_name in {
        "unavailable",
        "error",
        "no-hands",
        "mediapipe",
    }


def test_unavailable_reason_explains_a_missing_model_or_dependency():
    recognizer = GestureRecognizer()
    if recognizer.available:
        assert recognizer.unavailable_reason is None
    else:
        assert isinstance(recognizer.unavailable_reason, str)
