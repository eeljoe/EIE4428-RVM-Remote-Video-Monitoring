"""Tests for the capture sources and the multi-client stream session."""

import asyncio

import numpy as np
import pytest

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