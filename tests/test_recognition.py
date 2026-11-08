"""Face identification and expression classification.

Both stages depend on MediaPipe being installed *and* on the model file being
present, so the tests split in two: the parts that are pure arithmetic
(embedding comparison, blendshape weighting) are tested exactly, and the parts
that need the model only assert that every outcome is a reported state rather
than an exception.  A monitoring server that dies because an optional model is
missing is worse than one that says "unavailable".
"""

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from rvm.analysis.models import model_path, models_dir
from rvm.analysis.recognition import (
    EmotionDetection,
    EmotionRecognizer,
    FaceRecognition,
    FaceRecognizer,
    FaceSamplingError,
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


def test_a_registered_vector_of_another_width_is_skipped_rather_than_raised():
    """A hand-edited list must not take the analysis tick down with it.

    ``embedding - registered`` raises ``ValueError`` when the two widths
    differ, and nothing between ``recognize`` and the pump task catches it, so
    one stale entry stops the picture stream for good.  A vector that cannot
    be compared simply cannot match -- the face is reported as unknown, and the
    entries that do line up keep working.
    """
    recognizer = FaceRecognizer(threshold=0.6)
    recognizer.replace_known_faces({"stale": np.zeros(5), "joe": np.zeros(4)})

    # Hand-computed: distance norm(4 x 0.2) = 0.4, confidence 1 - 0.4 = 0.6.
    name, confidence = recognizer._match(np.full(4, 0.2))

    assert name == "joe"
    assert confidence == pytest.approx(0.6)


def test_matching_against_only_wrong_width_vectors_reports_nobody():
    recognizer = FaceRecognizer(threshold=0.6)
    recognizer.replace_known_faces({"stale": np.zeros(5)})

    assert recognizer._match(np.zeros(4)) == (None, 0.0)


# --------------------------------------------------------------------------
# Sampling one frame for registration
# --------------------------------------------------------------------------


def test_sampling_a_frame_without_a_face_returns_an_empty_list():
    """A blank picture has no face: an empty answer, not an exception.

    Registration turns this into ``no-face`` (the operator can fix it by
    standing in front of the camera), which only works if the sampler
    distinguishes "nothing there" from "no landmarker".
    """
    pytest.importorskip("mediapipe")

    recognizer = FaceRecognizer()
    try:
        assert recognizer.sample_faces(np.zeros((120, 160, 3), dtype=np.uint8)) == []
    finally:
        recognizer.close()


def test_sampling_without_a_model_is_reported_as_a_sampling_error(tmp_path, monkeypatch):
    """``unavailable`` is a 503, so the sampler must not answer "no face"."""
    monkeypatch.setenv("RVM_MODELS_DIR", str(tmp_path))
    recognizer = FaceRecognizer()

    with pytest.raises(FaceSamplingError):
        recognizer.sample_faces(np.zeros((120, 160, 3), dtype=np.uint8))


# --------------------------------------------------------------------------
# The registry is replaced, never edited in place
# --------------------------------------------------------------------------


def test_registering_a_face_leaves_the_previous_mapping_untouched():
    recognizer = FaceRecognizer()
    recognizer.add_known_face("joe", np.zeros(4))
    held = recognizer.known_faces

    recognizer.add_known_face("amy", np.ones(4))

    assert held is not recognizer.known_faces, "in-place insert is the bug this pins"
    assert list(held) == ["joe"]
    assert sorted(recognizer.known_faces) == ["amy", "joe"]


def test_removing_a_face_leaves_the_previous_mapping_untouched():
    recognizer = FaceRecognizer()
    recognizer.add_known_face("joe", np.zeros(4))
    held = recognizer.known_faces

    assert recognizer.remove_known_face("joe") is True
    assert recognizer.remove_known_face("joe") is False

    assert held is not recognizer.known_faces
    assert list(held) == ["joe"]
    assert recognizer.known_faces == {}


def test_replacing_the_list_installs_a_fresh_mapping():
    recognizer = FaceRecognizer()
    recognizer.add_known_face("old", np.zeros(4))
    held = recognizer.known_faces

    recognizer.replace_known_faces({"loaded": np.array([1.0, 2.0])})

    assert held is not recognizer.known_faces
    assert list(held) == ["old"]
    assert recognizer.known_faces["loaded"].tolist() == [1.0, 2.0]


def test_identifying_while_the_list_changes_never_raises():
    """What an in-place registry would do: ``dictionary changed size``.

    The encode thread walks ``known_faces`` on every analysed picture while a
    registration request replaces it.  Whole-mapping replacement means the
    walk holds one immutable dict, so the two cannot collide -- this test would
    fail with ``RuntimeError`` if the mapping were edited in place.
    """
    recognizer = FaceRecognizer(threshold=0.6)
    stop = threading.Event()
    failures: list[BaseException] = []

    def churn() -> None:
        index = 0
        while not stop.is_set():
            name = f"person-{index}"
            recognizer.add_known_face(name, np.zeros(4))
            recognizer.remove_known_face(name)
            index += 1

    worker = threading.Thread(target=churn, daemon=True)
    worker.start()
    try:
        for _ in range(400):
            try:
                recognizer._match(np.ones(4))
            except BaseException as exc:  # noqa: BLE001 - the failure is the assertion
                failures.append(exc)
                break
    finally:
        stop.set()
        worker.join(timeout=5.0)

    assert failures == []

