"""Tests for the parts that decide whether the demonstration works.

Everything in this module is about the delivery path rather than the codec:
the operator's page has to show a picture, the picture a remote station
receives has to be the one the codec produced, the recorded clip has to carry
the colours of the scene, and the counters on the dashboard have to mean what
they say.  A defect in any of these is invisible to a unit test of the
individual module and fatal on the day of the demonstration, which is why they
are pinned here together.
"""

from __future__ import annotations

import asyncio
import re

import numpy as np
import pytest

from rvm.codec.video import VideoDecoder, VideoEncoder
from rvm.network.packet import Packet
from rvm.network.stats import StreamStats
from rvm.server.session import StreamSession

WEB = "src/rvm/web"


def read_web(name: str) -> str:
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    return (root / WEB / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The operator's page
# --------------------------------------------------------------------------


def test_the_page_points_the_video_element_at_the_live_stream():
    """Without a src the element never loads and the operator sees a black box.

    The stream is the whole point of the project, so this is pinned as a
    regression test rather than left to a manual look.
    """
    html = read_web("index.html")

    match = re.search(r"<img[^>]*id=\"stream\"[^>]*>", html)

    assert match is not None, "the page has no video element"
    assert "src=" in match.group(0), "the video element has no src attribute"
    assert "stream.mjpg" in match.group(0)


def test_the_page_offers_both_the_camera_and_the_decoded_view():
    html = read_web("index.html")

    assert 'id="view-source"' in html
    assert 'id="view-decoded"' in html


def test_the_client_script_starts_the_stream_on_load():
    """The script must set the source itself, not only recover from an error."""
    script = read_web("app.js")

    assert "setView(" in script
    assert "/api/stream.mjpg?view=" in script


# --------------------------------------------------------------------------
# The decoded view
# --------------------------------------------------------------------------


def make_session(**kwargs):
    options = dict(width=160, height=96, fps=10.0, bitrate=300_000, gop_size=10)
    options.update(kwargs)
    return StreamSession(**options)


def test_the_session_publishes_both_pictures():
    session = make_session()
    asyncio.run(session.run_once())

    assert session.snapshot_jpeg(view="source") is not None
    assert session.snapshot_jpeg(view="decoded") is not None


def test_waiting_for_the_first_picture_gives_up_gracefully():
    session = make_session()

    assert asyncio.run(session.wait_for_picture(timeout=0.05)) is None


def test_the_decoded_picture_is_the_compressed_one():
    """The decoded view must be the reconstruction, not a copy of the source."""
    session = make_session()
    asyncio.run(session.run_once())

    source = session.snapshot_jpeg(view="source")
    decoded = session.snapshot_jpeg(view="decoded")

    assert source != decoded


def test_an_unknown_view_falls_back_to_the_source_picture():
    session = make_session()
    asyncio.run(session.run_once())

    assert session.snapshot_jpeg(view="nonsense") == session.snapshot_jpeg(view="source")


def test_the_encoder_reconstruction_is_what_the_decoder_produces():
    """The published decoded view must match a real decode of the bitstream.

    The server serves the encoder's reconstruction branch rather than running
    a second decoder, so the two have to agree exactly -- otherwise the
    demonstration would show a picture the receiver could never decode.
    """
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    decoder = VideoDecoder()
    scene = np.zeros((96, 128, 3), dtype=np.uint8)
    scene[:, :, 0] = 200
    scene[:, :, 2] = 60

    encoded = encoder.encode(scene, force_keyframe=True)
    decoded = decoder.decode(encoded)

    assert np.array_equal(encoder.reconstruction_rgb, decoded)


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def test_the_recorder_saves_the_colour_picture(tmp_path):
    """A clip saved in grey would not show the scene as the operator saw it."""
    cv2 = pytest.importorskip("cv2")

    session = make_session(record_dir=tmp_path / "clips")
    session.configure_recording(enabled=True)
    asyncio.run(session.run_once())
    session.configure_recording(enabled=False)

    clips = sorted((tmp_path / "clips").glob("*.jpg"))

    assert len(clips) == 1
    picture = cv2.imread(str(clips[0]))
    assert picture is not None
    # A grey picture has one identical channel repeated three times; a colour
    # scene does not.
    channels = [float(picture[:, :, index].mean()) for index in range(3)]
    assert max(channels) - min(channels) > 1.0


# --------------------------------------------------------------------------
# Counters
# --------------------------------------------------------------------------


def test_a_key_frame_is_counted_once_and_not_once_per_fragment():
    """A large intra picture is split into several packets; it is still one frame."""
    stats = StreamStats()

    stats.record_sent(Packet(0, 0, False, b"x"), now=0.0, is_keyframe=True)
    stats.record_sent(Packet(1, 0, False, b"x"), now=0.01, is_keyframe=True)
    stats.record_sent(Packet(2, 0, True, b"x"), now=0.02, is_keyframe=True)

    assert stats.pictures == 1
    assert stats.keyframes == 1


def test_a_predicted_picture_is_not_counted_as_a_key_frame():
    stats = StreamStats()

    stats.record_sent(Packet(0, 0, False, b"x"), now=0.0)
    stats.record_sent(Packet(1, 0, True, b"x"), now=0.01)

    assert stats.pictures == 1
    assert stats.keyframes == 0


# --------------------------------------------------------------------------
# The HTTP surface
# --------------------------------------------------------------------------


@pytest.fixture
async def client(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer

    from rvm.server.app import create_app

    session = StreamSession(
        width=160,
        height=96,
        fps=10.0,
        bitrate=300_000,
        record_dir=tmp_path / "clips",
    )
    app = create_app(session=session)
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    try:
        yield test_client
    finally:
        await test_client.close()


async def test_the_snapshot_endpoint_serves_the_decoded_view(client):
    response = await client.get("/api/snapshot.jpg?view=decoded")

    assert response.status == 200
    assert (await response.read())[:2] == b"\xff\xd8"


async def test_the_snapshot_endpoint_ignores_an_unknown_view(client):
    """A mistyped parameter should still show a picture, not an error."""
    response = await client.get("/api/snapshot.jpg?view=nonsense")

    assert response.status == 200
    assert (await response.read())[:2] == b"\xff\xd8"


async def test_the_decoded_view_is_not_the_source_view(client):
    source = await (await client.get("/api/snapshot.jpg?view=source")).read()
    decoded = await (await client.get("/api/snapshot.jpg?view=decoded")).read()

    assert source != decoded


async def test_the_stream_endpoint_honours_the_view_parameter(client):
    import aiohttp

    async with client.get(
        "/api/stream.mjpg?view=decoded",
        timeout=aiohttp.ClientTimeout(total=6),
    ) as response:
        chunk = await response.content.read(4096)

    assert response.status == 200
    assert b"--frame" in chunk
