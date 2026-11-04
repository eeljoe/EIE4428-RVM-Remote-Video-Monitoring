"""Face identification and expression classification.

Both stages depend on MediaPipe being installed *and* on the model file being
present, so the tests split in two: the parts that are pure arithmetic
(embedding comparison, blendshape weighting) are tested exactly, and the parts
that need the model only assert that every outcome is a reported state rather
than an exception.  A monitoring server that dies because an optional model is
missing is worse than one that says "unavailable".
"""

from types import SimpleNamespace

import numpy as np
import pytest

from rvm.analysis.models import model_path, models_dir
from rvm.analysis.recognition import (
    EmotionDetection,
    EmotionRecognizer,
    FaceRecognition,
    FaceRecognizer,
    _ensure_rgb,
    _boxes_from_landmarks,
)


def blendshapes(**scores):
    """A MediaPipe blendshape list from ``name=score`` keyword pairs."""
    return [SimpleNamespace(category_name=name, score=value) for name, value in scores.items()]


# --------------------------------------------------------------------------
# Model location
# --------------------------------------------------------------------------


def test_models_directory_is_found_in_a_source_checkout(monkeypatch):
    monkeypatch.delenv("RVM_MODELS_DIR", raising=False)
    directory = models_dir()
    assert directory is not None
    assert (directory / "face_landmarker.task").is_file()


def test_an_explicit_models_directory_wins(tmp_path, monkeypatch):
    (tmp_path / "face_landmarker.task").write_bytes(b"stub")
    monkeypatch.setenv("RVM_MODELS_DIR", str(tmp_path))
    assert model_path("face_landmarker.task") == tmp_path / "face_landmarker.task"


def test_a_missing_model_names_what_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("RVM_MODELS_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError, match="hand_landmarker.task"):
        model_path("hand_landmarker.task")


# --------------------------------------------------------------------------
# Colour handling
# --------------------------------------------------------------------------


def test_a_grey_frame_is_expanded_to_rgb():
    rgb = _ensure_rgb(np.zeros((10, 20), dtype=np.uint8))
    assert rgb.shape == (10, 20, 3)


def test_an_rgb_frame_is_passed_through_unchanged():
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    assert np.array_equal(_ensure_rgb(frame), frame)


def test_boxes_are_clamped_to_the_picture():
    landmarks = [
        SimpleNamespace(x=-0.1, y=-0.1, z=0.0),
        SimpleNamespace(x=1.2, y=1.2, z=0.0),
    ]
    assert _boxes_from_landmarks(landmarks, width=100, height=50) == (0, 0, 100, 50)


# --------------------------------------------------------------------------
# Expression classification: the pure half
# --------------------------------------------------------------------------


def test_a_smile_is_classified_as_happy():
    emotion, confidence = EmotionRecognizer()._classify(
        blendshapes(
            mouthSmileLeft=0.9, mouthSmileRight=0.9, cheekSquintLeft=0.9, cheekSquintRight=0.9
        )
    )
    assert emotion == "happy"
    assert confidence == pytest.approx(0.9)


def test_a_flat_face_is_reported_as_neutral():
    assert EmotionRecognizer()._classify(blendshapes()) == ("neutral", 0.2)


def test_brows_down_with_a_pressed_mouth_is_angry_not_sad():
    emotion, _ = EmotionRecognizer()._classify(
        blendshapes(
            browDownLeft=1.0,
            browDownRight=1.0,
            jawForward=1.0,
            mouthPressLeft=1.0,
            mouthPressRight=1.0,
        )
    )
    assert emotion == "angry"


def test_raised_outer_brows_with_wide_eyes_is_surprise():
    emotion, _ = EmotionRecognizer()._classify(
        blendshapes(
            browOuterUpLeft=1.0,
            browOuterUpRight=1.0,
            eyeWideLeft=1.0,
            eyeWideRight=1.0,
            jawOpen=1.0,
        )
    )
    assert emotion == "surprise"


def test_a_weak_dominant_score_stays_neutral():
    emotion, confidence = EmotionRecognizer()._classify(blendshapes(mouthSmileLeft=0.1))
    assert emotion == "neutral"
    assert confidence == 0.2


# --------------------------------------------------------------------------
# Face database: the pure half
# --------------------------------------------------------------------------


def test_a_registered_face_can_be_removed_again():
    recognizer = FaceRecognizer()
    recognizer.add_known_face("joe", np.ones(6))
    assert recognizer.remove_known_face("joe") is True
    assert recognizer.remove_known_face("joe") is False


def test_the_nearest_registered_face_is_the_match():
    recognizer = FaceRecognizer()
    recognizer.add_known_face("near", np.zeros(4))
    recognizer.add_known_face("far", np.full(4, 10.0))
    name, distance = recognizer._nearest(np.ones(4))
    assert name == "near"
    assert distance == pytest.approx(2.0)


def test_an_unrecognisable_face_is_dropped_rather_than_guessed():
    recognizer = FaceRecognizer(threshold=0.6)
    recognizer.add_known_face("someone", np.zeros(4))
    # Distance 4.0 means confidence -3: far below the threshold.
    embedding = np.full(4, 2.0)
    name, distance = recognizer._nearest(embedding)
    assert name == "someone"
    assert 1.0 - distance < recognizer.threshold


# --------------------------------------------------------------------------
# Reported states, with or without MediaPipe installed
# --------------------------------------------------------------------------


def test_recognition_on_a_blank_frame_reports_a_state():
    result = FaceRecognizer().recognize(np.zeros((120, 160, 3), dtype=np.uint8))
    assert isinstance(result, FaceRecognition)
    assert result.state in {"unavailable", "error", "no-faces", "no-known-faces"}
    assert result.count == 0


def test_emotion_detection_on_a_blank_frame_reports_a_state():
    result = EmotionRecognizer().detect(np.zeros((120, 160, 3), dtype=np.uint8))
    assert isinstance(result, EmotionDetection)
    assert result.state in {"unavailable", "error", "no-faces"}
    assert result.count == 0


# --------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------


def test_face_snapshot_rounds_confidence_and_lists_the_box():
    recognition = FaceRecognition([("joe", 0.81234, (1, 2, 3, 4))], "mediapipe")
    snapshot = recognition.snapshot()
    assert snapshot["count"] == 1
    assert snapshot["identities"][0] == {
        "name": "joe",
        "confidence": 0.812,
        "bbox": [1, 2, 3, 4],
    }
    assert snapshot["state"] == "mediapipe"


def test_emotion_snapshot_rounds_confidence_and_names_the_state():
    detection = EmotionDetection([("happy", 0.4567, (1, 2, 3, 4))], "mediapipe")
    snapshot = detection.snapshot()
    assert snapshot["count"] == 1
    assert snapshot["emotions"][0]["emotion"] == "happy"
    assert snapshot["emotions"][0]["confidence"] == 0.457
    assert snapshot["state"] == "mediapipe"



# --------------------------------------------------------------------------
# The models the analysers actually load
# --------------------------------------------------------------------------


def test_the_face_models_load_and_can_be_closed():
    """A wrong keyword or a bad model path would leave this "unavailable".

    Pinned on purpose: the port fixed exactly that class of bug in the gesture
    module (a misspelt option swallowed into "unavailable"), and no other test
    in the suite would notice a repeat.
    """
    pytest.importorskip("mediapipe")

    for factory in (FaceRecognizer, EmotionRecognizer):
        recognizer = factory()
        try:
            assert recognizer.available is True, recognizer.unavailable_reason
        finally:
            recognizer.close()
        assert recognizer.available is False, "a closed recogniser must not reload itself"


def test_a_missing_model_is_reported_rather_than_raised(tmp_path, monkeypatch):
    monkeypatch.setenv("RVM_MODELS_DIR", str(tmp_path))

    recognizer = FaceRecognizer()

    assert recognizer.available is False
    assert "face_landmarker.task" in (recognizer.unavailable_reason or "")


def test_a_face_further_than_the_threshold_is_not_reported():
    recognizer = FaceRecognizer(threshold=0.6)
    recognizer.add_known_face("someone", np.zeros(4))

    name, confidence = recognizer._match(np.full(4, 2.0))

    assert name is None
    assert confidence < recognizer.threshold


def test_a_face_inside_the_threshold_is_reported_with_its_name():
    recognizer = FaceRecognizer(threshold=0.6)
    recognizer.add_known_face("joe", np.zeros(4))

    name, confidence = recognizer._match(np.full(4, 0.2))

    assert name == "joe"
    assert confidence == pytest.approx(0.6)

