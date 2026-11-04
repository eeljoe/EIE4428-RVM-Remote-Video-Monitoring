"""Tests for the capture sources and the multi-client stream session."""

import asyncio
import threading
import time

import numpy as np
import pytest

from rvm.audio import AudioCapture
from rvm.server.session import StreamSession
from rvm.server.source import CameraSource, SyntheticSource, open_source


# --------------------------------------------------------------------------
# Capture sources
# --------------------------------------------------------------------------


def test_synthetic_source_yields_the_requested_frame_size():
    source = SyntheticSource(160, 96, fps=10.0)

    frame = source.read()

    assert frame.shape == (96, 160, 3)
    assert frame.dtype == np.uint8


def test_synthetic_source_advances_between_reads():
    source = SyntheticSource(160, 96, fps=10.0)

    first = source.read()
    second = source.read()

    assert not np.array_equal(first, second)


def test_synthetic_source_moves_a_bright_object_across_the_view():
    """The scene must actually contain motion for the detector to find."""
    source = SyntheticSource(160, 96, fps=10.0)

    early = source.read().astype(int)
    later = source.read().astype(int)

    assert np.abs(later - early).max() > 20


def test_synthetic_source_reports_its_properties():
    source = SyntheticSource(320, 240, fps=15.0)

    assert source.width == 320
    assert source.height == 240
    assert source.fps == pytest.approx(15.0)


def test_synthetic_source_rejects_dimensions_that_are_not_block_aligned():
    with pytest.raises(ValueError, match="multiple of 16"):
        SyntheticSource(162, 96)


def test_synthetic_source_paces_itself_to_the_frame_rate():
    source = SyntheticSource(160, 96, fps=25.0)

    elapsed = source._pace(period_index=25)  # one simulated second

    assert elapsed is None or elapsed >= 0


def test_camera_source_reports_unavailable_without_a_camera():
    source = CameraSource(index=99)

    assert source.available is False


def test_camera_source_read_returns_none_when_unavailable():
    source = CameraSource(index=99)
    source.open()

    assert source.read() is None


def test_open_source_falls_back_to_the_synthetic_generator():
    """A machine with no webcam must still be able to demonstrate the system."""
    source = open_source(prefer_camera=True, width=160, height=96)

    assert source.read() is not None


def test_open_source_can_skip_the_camera_entirely():
    source = open_source(prefer_camera=False, width=160, height=96)

    assert isinstance(source, SyntheticSource)


def test_a_source_releases_cleanly():
    source = SyntheticSource(160, 96)
    source.read()

    source.close()

    assert source.closed is True


# --------------------------------------------------------------------------
# Stream session
# --------------------------------------------------------------------------


def make_session(**kwargs):
    options = dict(width=160, height=96, fps=10.0, bitrate=300_000, gop_size=10)
    options.update(kwargs)
    return StreamSession(**options)


def test_session_produces_encoded_pictures():
    session = make_session()

    encoded = asyncio.run(session.run_once())

    assert encoded is not None
    assert len(encoded.data) > 0


def test_session_emits_a_keyframe_first():
    session = make_session()

    encoded = asyncio.run(session.run_once())

    assert encoded.is_keyframe


def test_session_publishes_a_snapshot_a_client_can_grab():
    session = make_session()
    asyncio.run(session.run_once())

    assert session.snapshot_jpeg() is not None


def test_snapshot_is_a_jpeg():
    session = make_session()
    asyncio.run(session.run_once())

    jpeg = session.snapshot_jpeg()

    assert jpeg[:2] == b"\xff\xd8"  # JPEG SOI marker


def test_session_tracks_the_measured_frame_rate():
    session = make_session()
    for _ in range(6):
        asyncio.run(session.run_once())

    assert session.status()["frame_rate"] > 0.0


def test_session_reports_the_current_qp_and_bitrate():
    session = make_session()
    for _ in range(4):
        asyncio.run(session.run_once())

    status = session.status()

    assert 1 <= status["qp"] <= 51
    assert status["bitrate"] >= 0.0


def test_session_reports_motion_detection_results():
    session = make_session()
    for _ in range(4):
        asyncio.run(session.run_once())

    status = session.status()

    assert "alarm" in status
    assert "motion_ratio" in status


def test_session_registers_and_removes_clients():
    session = make_session()

    client = session.add_client()
    assert session.client_count == 1

    session.remove_client(client.id)
    assert session.client_count == 0


def test_session_delivers_the_latest_picture_to_a_client():
    session = make_session()
    client = session.add_client()
    asyncio.run(session.run_once())

    packet = asyncio.run(client.get())

    assert packet is not None


def test_a_client_receives_the_latest_picture_even_if_it_falls_behind():
    """Live video is worthless once stale: a slow client skips to the newest."""
    session = make_session()
    client = session.add_client(max_queue=1)
    for _ in range(4):
        asyncio.run(session.run_once())

    first = asyncio.run(client.get())

    assert first is not None


def test_session_counts_frames_delivered_per_client():
    session = make_session()
    client = session.add_client()
    for _ in range(3):
        asyncio.run(session.run_once())

    assert client.pictures_delivered == 3
    assert client.packets_delivered >= 3


def test_session_reports_the_number_of_connected_clients():
    session = make_session()
    session.add_client()
    session.add_client()

    assert session.status()["clients"] == 2


def test_session_raises_the_alarm_when_the_scene_changes():
    session = make_session(motion_threshold=0.01)
    static = session.source.read()

    # The first picture becomes the background, so a frozen scene stays quiet.
    for _ in range(5):
        session.inject_frame(static)
        asyncio.run(session.run_once())
    assert session.status()["alarm"] is False

    session.inject_frame(np.zeros((96, 160, 3), dtype=np.uint8))
    asyncio.run(session.run_once())

    assert session.status()["alarm"] is True


def test_session_can_start_and_stop_recording(tmp_path):
    session = make_session(record_dir=tmp_path / "clips")
    session.configure_recording(enabled=True)

    asyncio.run(session.run_once())
    session.configure_recording(enabled=False)

    assert session.recording is False


def test_session_status_is_json_friendly():
    import json

    session = make_session()
    asyncio.run(session.run_once())

    json.dumps(session.status())


def test_session_rejects_a_configuration_it_cannot_deliver():
    session = make_session()

    with pytest.raises(ValueError, match="bitrate"):
        session.update_config(bitrate=-1)

# --------------------------------------------------------------------------
# Optional analysis wiring
# --------------------------------------------------------------------------


def test_analysis_is_off_unless_it_is_asked_for():
    """The analysers cost tens of ms per picture, so they are opt-in."""
    session = make_session()

    features = session.features()

    assert features["enabled"] is False
    assert features["face_recognition"] is False
    assert features["emotion_recognition"] is False
    assert features["gesture_recognition"] is False
    assert session.status()["analysis"]["ready"] is False


def test_status_carries_the_analysis_sections_even_when_idle():
    session = make_session()
    asyncio.run(session.run_once())

    status = session.status()

    for key, field in (
        ("face_identities", "identities"),
        ("emotions", "emotions"),
        ("gestures", "gestures"),
    ):
        assert status[key]["count"] == 0
        assert status[key][field] == []
    assert status["audio_events"] == 0
    assert status["audio_last"] is None


def test_analysis_stays_idle_until_the_models_are_loaded():
    """Enabling analysis must not block the encode thread on a model load."""
    session = make_session()
    session.analysis_enabled = True  # warm-up deliberately not started

    asyncio.run(session.run_once())

    assert session.status()["gestures"]["count"] == 0
    assert session.status()["emotions"]["count"] == 0
    assert session.features()["ready"] is False


def test_analysis_status_matches_the_telemetry_shape():
    session = make_session()
    asyncio.run(session.run_once())

    analysis = session.analysis_status()
    status = session.status()

    assert analysis["tracks"] == {"count": len(status["tracks"]), "tracks": status["tracks"]}
    assert analysis["gestures"] == status["gestures"]
    assert set(analysis) == {
        "tracks",
        "face_identities",
        "emotions",
        "gestures",
        "audio",
        "features",
    }


def fake_start(self):
    self._running = True
    return True


def fake_stop(self):
    self._running = False


def test_audio_control_reports_whether_the_microphone_is_running(monkeypatch):
    monkeypatch.setattr(AudioCapture, "start", fake_start)
    monkeypatch.setattr(AudioCapture, "stop", fake_stop)
    session = make_session()
    try:
        assert session.set_audio_enabled(True) is True
        assert session.audio_enabled is True

        assert session.set_audio_enabled(False) is False
        assert session.audio_enabled is False
    finally:
        session.close()


def test_audio_monitoring_does_not_depend_on_video_analysis(monkeypatch):
    """``--no-analysis`` must not leave a running microphone that never reports.

    Audio is its own switch.  Gating it behind the video analysis flag made
    ``POST /api/audio/control`` answer "running" while no event could ever be
    produced.
    """
    monkeypatch.setattr(AudioCapture, "start", fake_start)
    session = make_session()  # analysis off
    session.set_audio_enabled(True)

    loud = (0.5 * np.sin(2 * np.pi * 100 * np.arange(1024) / 16000.0) * 32767).astype(np.int16)
    monkeypatch.setattr(session.audio_capture, "read", lambda timeout=0.0: loud)

    try:
        asyncio.run(session.run_once())
        audio = session.analysis_status()["audio"]
        assert session.features()["enabled"] is False, "analysis stays off"
        assert audio["running"] is True
        assert audio["count"] >= 1, "audio must be drained outside the analysis gate"
    finally:
        session.close()


def test_the_audio_section_of_the_analysis_status_is_shaped_for_the_api():
    session = make_session()

    assert session.analysis_status()["audio"] == {
        "count": 0,
        "events": [],
        "running": False,
    }



def test_a_tick_publishes_all_three_results_as_one_tuple():
    """``status()`` must never report a half-applied tick.

    The three analysers finish at different times; publishing them field by
    field let a reader see face results from one tick next to gestures from the
    previous one.  One tuple assignment is the whole fix, so the test pins the
    shape: whatever ``_analyse`` produced this tick is what readers see.
    """

    class Stub:
        count = 0
        state = "mediapipe"

        def __init__(self):
            self.marker = id(self)

        def snapshot(self):
            return {"count": 0, "state": self.state, "marker": self.marker}

    session = make_session()
    session.analysis_enabled = True
    session._models_ready.set()
    session.analysis_interval = 0.0

    stubs = (Stub(), Stub(), Stub())
    session.face_recognizer.recognize = lambda frame: stubs[0]
    session.emotion_recognizer.detect = lambda frame: stubs[1]
    session.gesture_recognizer.detect = lambda frame: stubs[2]

    session._analyse(np.zeros((8, 8, 3), dtype=np.uint8))

    published = session._analysis_view
    assert published == stubs
    status = session.status()
    assert status["face_identities"]["marker"] == stubs[0].marker
    assert status["emotions"]["marker"] == stubs[1].marker
    assert status["gestures"]["marker"] == stubs[2].marker

def test_features_does_not_probe_the_microphone():
    """``status()`` calls features() twice a second; it must not open PortAudio."""
    session = make_session()
    capture = session._audio_capture()
    assert capture.availability is None

    features = session.features()

    assert features["audio_available"] is None
    assert capture._pyaudio is None, "features() must not construct PyAudio"


def test_the_audio_capture_is_created_once_under_concurrency(monkeypatch):
    """Two AudioCapture objects mean two PyAudio contexts and a crash.

    Construction is slowed down so the window is wide enough for eight threads
    to fall into it; without the lock this test builds eight objects.
    """
    import rvm.audio.capture as capture_module

    original_init = capture_module.AudioCapture.__init__
    constructions = []
    guard = threading.Lock()

    def slow_init(self, config=None):
        original_init(self, config)
        with guard:
            constructions.append(1)
        time.sleep(0.02)

    monkeypatch.setattr(capture_module.AudioCapture, "__init__", slow_init)
    session = make_session()
    barrier = threading.Barrier(8)

    def grab():
        barrier.wait()
        session._audio_capture()

    created = []
    threads = [threading.Thread(target=lambda: created.append(session._audio_capture())) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(constructions) == 1, "the capture must be constructed once"
    assert len({id(capture) for capture in created}) == 1, "every caller gets the same object"
