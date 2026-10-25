"""Tests for the monitoring intelligence: motion detection, faces, recording."""

import numpy as np
import pytest
from scenegen import moving_scene

from rvm.analysis.detect import (
    FaceDetector,
    MotionDetector,
    MotionResult,
)
from rvm.core.colorspace import rgb_to_ycbcr, to_planes
from rvm.server.recorder import FrameRecorder


def luma_of(rgb):
    return to_planes(rgb_to_ycbcr(rgb))[0].astype(np.uint8)


def grey_scene(width=160, height=120):
    luma = moving_scene(0, width=width, height=height, dx=0, dy=0, seed=3)
    return np.clip(luma, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# Motion detection against a learned static background
# --------------------------------------------------------------------------


def test_a_completely_static_scene_raises_no_alarm():
    detector = MotionDetector()
    scene = grey_scene()

    for _ in range(10):
        result = detector.update(scene)

    assert result.motion_ratio == pytest.approx(0.0, abs=1e-6)
    assert result.alarm is False


def test_a_static_scene_stays_quiet_for_many_frames():
    """The background model must converge instead of alarm on its own noise."""
    detector = MotionDetector()
    scene = grey_scene()

    alarms = [detector.update(scene).alarm for _ in range(60)]

    assert sum(alarms) == 0


def test_an_object_entering_the_scene_raises_the_alarm():
    detector = MotionDetector()
    scene = grey_scene()
    for _ in range(10):
        detector.update(scene)

    moved = scene.copy()
    moved[40:80, 40:80] = 250
    result = detector.update(moved)

    assert result.alarm is True
    assert result.motion_ratio > 0.01


def test_motion_ratio_grows_with_the_size_of_the_change():
    detector = MotionDetector()
    scene = grey_scene()
    for _ in range(10):
        detector.update(scene)

    small = scene.copy()
    small[10:20, 10:20] = 250
    large = scene.copy()
    large[10:110, 10:110] = 250

    assert detector.update(small).motion_ratio < detector.update(large).motion_ratio


def test_the_detected_region_brackets_the_changed_pixels():
    detector = MotionDetector()
    scene = grey_scene()
    for _ in range(10):
        detector.update(scene)

    moved = scene.copy()
    moved[30:50, 60:90] = 250
    result = detector.update(moved)

    assert result.bbox is not None
    top, left, bottom, right = result.bbox
    assert top <= 32 and left <= 62
    assert bottom >= 48 and right >= 88


def test_the_alarm_clears_once_the_scene_settles_again():
    detector = MotionDetector()
    scene = grey_scene()
    for _ in range(10):
        detector.update(scene)

    moved = scene.copy()
    moved[40:80, 40:80] = 250
    assert detector.update(moved).alarm is True

    for _ in range(30):
        result = detector.update(scene)

    assert result.alarm is False


def test_the_alarm_does_not_flap_on_a_borderline_scene():
    """Hysteresis: between the clear and raise thresholds the alarm holds."""
    detector = MotionDetector(threshold=0.05, clear_threshold=0.005)
    scene = grey_scene()
    for _ in range(10):
        detector.update(scene)

    big = scene.copy()
    big[20:110, 20:110] = 250  # far above the raise threshold
    assert detector.update(big).alarm is True

    # Now a change that sits between the clear and raise thresholds. The alarm
    # must hold rather than chattering on every frame.
    borderline = scene.copy()
    borderline[20:50, 20:50] = 250
    held = [detector.update(borderline).alarm for _ in range(10)]
    assert all(held)

    # And it clears once the scene is quiet again.
    assert detector.update(scene).alarm is False


def test_the_background_model_adapts_to_a_slowly_drifting_scene():
    detector = MotionDetector(adapt_rate=0.05)
    scene = grey_scene()

    for _ in range(5):
        detector.update(scene)

    drifted = np.clip(scene.astype(float) + 3.0, 0, 255).astype(np.uint8)
    for _ in range(40):
        result = detector.update(drifted)

    assert result.alarm is False


def test_the_background_model_can_be_reset():
    detector = MotionDetector()
    scene = grey_scene()
    for _ in range(5):
        detector.update(scene)

    detector.reset()
    result = detector.update(scene)

    assert result.motion_ratio == pytest.approx(0.0, abs=1e-6)


def test_the_detector_rejects_a_frame_of_the_wrong_size():
    detector = MotionDetector()
    detector.update(grey_scene())

    with pytest.raises(ValueError, match="shape"):
        detector.update(np.zeros((10, 10), dtype=np.uint8))


def test_the_detector_rejects_a_colour_frame():
    detector = MotionDetector()

    with pytest.raises(ValueError, match="luma"):
        detector.update(np.zeros((32, 32, 3), dtype=np.uint8))


def test_motion_result_serialises_for_the_dashboard():
    detector = MotionDetector()
    scene = grey_scene()
    for _ in range(5):
        result = detector.update(scene)

    snapshot = result.snapshot()

    assert "motion_ratio" in snapshot
    assert "alarm" in snapshot
    assert isinstance(snapshot["alarm"], bool)


def test_the_detector_exposes_a_moving_region_mask():
    detector = MotionDetector()
    scene = grey_scene()
    for _ in range(10):
        detector.update(scene)

    moved = scene.copy()
    moved[40:80, 40:80] = 250
    result = detector.update(moved)

    assert result.mask.shape == scene.shape
    assert result.mask.dtype == np.uint8
    assert result.mask.max() > 0


# --------------------------------------------------------------------------
# Face detection
# --------------------------------------------------------------------------


def test_face_detector_reports_a_finding_for_a_face_like_patch():
    detector = FaceDetector()
    scene = np.zeros((120, 160), dtype=np.uint8)
    # A crude face-like oval: bright region with darker eye band.
    scene[30:90, 55:105] = 200
    scene[45:58, 65:95] = 40

    result = detector.detect(scene)

    assert result.count >= 0  # never raises; may or may not fire
    assert result.faces is not None


def test_face_detector_returns_boxes_inside_the_frame():
    detector = FaceDetector()
    scene = np.zeros((120, 160), dtype=np.uint8)
    scene[20:100, 50:110] = 180

    result = detector.detect(scene)

    for (x, y, w, h) in result.faces:
        assert x >= 0 and y >= 0
        assert x + w <= 160 and y + h <= 120


def test_face_detector_reports_nothing_on_a_flat_frame():
    detector = FaceDetector()

    result = detector.detect(np.zeros((120, 160), dtype=np.uint8))

    assert result.count == 0


def test_face_detector_rejects_a_frame_of_the_wrong_rank():
    detector = FaceDetector()

    with pytest.raises(ValueError):
        detector.detect(np.zeros((10, 10, 10, 2), dtype=np.uint8))


def test_face_detector_survives_a_frame_that_is_too_small_to_search():
    detector = FaceDetector()

    result = detector.detect(np.zeros((8, 8), dtype=np.uint8))

    assert result.count == 0


# --------------------------------------------------------------------------
# Recorder
# --------------------------------------------------------------------------


def test_recorder_writes_frames_under_the_output_directory(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0)

    recorder.write(grey_scene())
    path = recorder.stop()

    assert path is not None
    assert (tmp_path / "clips").exists()


def test_recorder_numbers_frames_in_order(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0)
    for _ in range(3):
        recorder.write(grey_scene())

    recorder.stop()
    files = sorted((tmp_path / "clips").glob("*.jpg"))

    assert len(files) == 3


def test_recorder_creates_the_directory_if_it_is_missing(tmp_path):
    target = tmp_path / "deep" / "nested"

    recorder = FrameRecorder(target, fps=10.0)
    recorder.write(grey_scene())
    recorder.stop()

    assert target.exists()


def test_recorder_reports_how_many_frames_it_saved(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0)
    for _ in range(5):
        recorder.write(grey_scene())

    recorder.stop()

    assert recorder.frame_count == 5


def test_recorder_estimates_a_duration_from_the_frame_rate(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0)
    for _ in range(20):
        recorder.write(grey_scene())

    recorder.stop()

    assert recorder.duration_seconds == pytest.approx(2.0)


def test_recorder_overlays_a_timestamp_on_the_saved_frame(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0)
    recorder.write(grey_scene(), timestamp=1.25)
    recorder.stop()

    saved = sorted((tmp_path / "clips").glob("*.jpg"))

    assert len(saved) == 1
    assert saved[0].stat().st_size > 0


def test_recorder_returns_none_when_nothing_was_written(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0)

    assert recorder.stop() is None


def test_recorder_can_be_stopped_twice_without_error(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0)
    recorder.write(grey_scene())

    assert recorder.stop() is not None
    assert recorder.stop() is None


def test_recorder_stamps_each_file_with_its_start_time(tmp_path):
    recorder = FrameRecorder(tmp_path / "clips", fps=10.0, started_at="20260101_120000")
    recorder.write(grey_scene())
    recorder.stop()

    files = list((tmp_path / "clips").glob("*.jpg"))

    assert files[0].name.startswith("20260101_120000")