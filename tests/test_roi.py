"""ROI-restricted motion detection and the monitoring controls it needs.

These tests were written before the feature: a monitoring camera usually has
places where movement does not matter -- a corridor behind glass, a tree in
wind, the owner walking past the door.  Confining detection to a region the
operator draws is the difference between a useful alarm and one that is
switched off after ten minutes.
"""

import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer

from rvm.analysis.detect import MotionDetector, sensitivity_settings
from rvm.server.app import create_app
from rvm.server.session import StreamSession

WIDTH, HEIGHT = 160, 112


def flat_scene(value=100):
    return np.full((HEIGHT, WIDTH), value, dtype=np.uint8)


def with_patch(frame, y, x, height=16, width=24, delta=15):
    frame = frame.copy()
    frame[y : y + height, x : x + width] += delta
    return frame


# --------------------------------------------------------------------------
# Detector level
# --------------------------------------------------------------------------


def test_motion_outside_the_region_of_interest_is_ignored():
    detector = MotionDetector()
    scene = flat_scene()
    for _ in range(5):
        detector.update(scene, roi=(0.5, 0.5, 1.0, 1.0))

    # Top-left patch: outside the bottom-right region the operator selected.
    result = detector.update(with_patch(scene, 5, 5), roi=(0.5, 0.5, 1.0, 1.0))

    assert result.alarm is False
    assert result.motion_ratio == pytest.approx(0.0)


def test_motion_inside_the_region_of_interest_raises_the_alarm():
    detector = MotionDetector()
    scene = flat_scene()
    for _ in range(5):
        detector.update(scene, roi=(0.5, 0.5, 1.0, 1.0))

    result = detector.update(with_patch(scene, 70, 90), roi=(0.5, 0.5, 1.0, 1.0))

    assert result.alarm is True
    assert result.motion_ratio > 0.0


def test_the_reported_box_is_in_full_frame_coordinates():
    detector = MotionDetector()
    scene = flat_scene()
    roi = (0.5, 0.5, 1.0, 1.0)
    for _ in range(120):
        detector.update(scene, roi=roi)

    result = detector.update(with_patch(scene, 70, 90), roi=roi)

    assert result.bbox is not None
    top, left = result.bbox[0], result.bbox[1]
    assert top >= HEIGHT // 2 - 2 and left >= WIDTH // 2 - 2


def test_without_a_region_the_whole_frame_is_monitored():
    detector = MotionDetector()
    scene = flat_scene()
    for _ in range(5):
        detector.update(scene)

    assert detector.update(with_patch(scene, 5, 5)).alarm is True


def test_sensitivity_levels_are_ordered_from_quiet_to_eager():
    low = sensitivity_settings("low")
    medium = sensitivity_settings("medium")
    high = sensitivity_settings("high")

    assert low["threshold"] > medium["threshold"] > high["threshold"]
    assert low["sensitivity"] > medium["sensitivity"] > high["sensitivity"]


def test_high_sensitivity_alarms_where_low_stays_quiet():
    """Same footage, different operating point: that is what the control buys."""
    scene = flat_scene()
    faded = with_patch(scene, 40, 40)  # +15 levels over 2% of the frame

    results = {}
    for level in ("low", "high"):
        detector = MotionDetector(**sensitivity_settings(level))
        for _ in range(5):
            detector.update(scene)
        results[level] = detector.update(faded).alarm

    assert results["high"] is True
    assert results["low"] is False


def test_reconfiguring_the_detector_relearns_the_scene():
    detector = MotionDetector()
    detector.update(with_patch(flat_scene(), 5, 5))  # alarm raised

    detector.configure(**sensitivity_settings("high"))

    # The first frame after reconfiguration only teaches the background, so
    # the alarm must not stay stuck on from before.
    assert detector.update(flat_scene()).alarm is False
    assert detector.has_background is True


def test_an_unknown_sensitivity_name_is_rejected():
    with pytest.raises(ValueError, match="sensitivity"):
        sensitivity_settings("extreme")


# --------------------------------------------------------------------------
# Session level
# --------------------------------------------------------------------------


def session():
    return StreamSession(width=WIDTH, height=HEIGHT, fps=10.0, bitrate=300_000)


def test_session_stores_a_normalised_region():
    s = session()

    s.set_roi((0.25, 0.25, 0.75, 0.75))

    assert s.roi == (0.25, 0.25, 0.75, 0.75)
    assert s.status()["roi"] == [0.25, 0.25, 0.75, 0.75]


@pytest.mark.parametrize(
    "bad",
    [
        (0.5, 0.5, 0.25, 0.25),  # inverted
        (0.0, 0.0, 0.0, 1.0),  # zero width
        (-0.1, 0.0, 1.0, 1.0),  # out of range
        (0.0, 0.0, 1.0),  # wrong length
    ],
)
def test_session_rejects_an_impossible_region(bad):
    with pytest.raises(ValueError):
        session().set_roi(bad)


def test_session_clears_the_region():
    s = session()
    s.set_roi((0.1, 0.1, 0.5, 0.5))

    s.set_roi(None)

    assert s.roi is None
    assert s.status()["roi"] is None


def test_session_exposes_the_sensitivity_level():
    s = session()

    s.set_motion_sensitivity("high")

    assert s.status()["motion_sensitivity"] == "high"
    assert s.motion_detector.sensitivity == pytest.approx(
        sensitivity_settings("high")["sensitivity"]
    )


def test_session_rejects_an_unknown_sensitivity_level():
    with pytest.raises(ValueError):
        session().set_motion_sensitivity("turbo")


# --------------------------------------------------------------------------
# HTTP surface
# --------------------------------------------------------------------------


@pytest.fixture
async def client(tmp_path):
    s = StreamSession(
        width=WIDTH,
        height=HEIGHT,
        fps=10.0,
        bitrate=300_000,
        record_dir=tmp_path / "clips",
    )
    app = create_app(session=s)
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    try:
        yield test_client
    finally:
        await test_client.close()


async def test_the_motion_endpoint_sets_the_region(client):
    response = await client.post("/api/motion", json={"roi": [0.2, 0.2, 0.8, 0.8]})

    assert response.status == 200
    assert (await response.json())["roi"] == [0.2, 0.2, 0.8, 0.8]


async def test_the_motion_endpoint_clears_the_region(client):
    await client.post("/api/motion", json={"roi": [0.2, 0.2, 0.8, 0.8]})

    response = await client.post("/api/motion", json={"roi": None})

    assert response.status == 200
    assert (await response.json())["roi"] is None


async def test_the_motion_endpoint_rejects_an_impossible_region(client):
    response = await client.post("/api/motion", json={"roi": [0.8, 0.8, 0.2, 0.2]})

    assert response.status == 400


async def test_the_motion_endpoint_sets_the_sensitivity(client):
    response = await client.post("/api/motion", json={"sensitivity": "low"})

    assert response.status == 200
    assert (await response.json())["motion_sensitivity"] == "low"


async def test_the_motion_endpoint_rejects_an_unknown_sensitivity(client):
    response = await client.post("/api/motion", json={"sensitivity": "turbo"})

    assert response.status == 400


async def test_a_recorded_frame_can_be_previewed(client, tmp_path):
    clips = tmp_path / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    (clips / "20260101_120000_000000.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    response = await client.get("/api/clips/20260101_120000/0.jpg")

    assert response.status == 200
    assert response.headers["Content-Type"] == "image/jpeg"


async def test_an_unknown_clip_frame_is_a_404(client):
    response = await client.get("/api/clips/20260101_120000/7.jpg")

    assert response.status == 404


async def test_the_page_offers_the_zone_sensitivity_and_clip_panels(client):
    page = await (await client.get("/")).text()

    assert 'id="roi"' in page
    assert 'id="sensitivity"' in page
    assert 'id="clear-roi"' in page
    assert 'id="clips"' in page


async def test_the_client_script_drives_the_new_controls(client):
    script = await (await client.get("/static/app.js")).text()

    assert "/api/motion" in script
    assert "pointerdown" in script
    assert "/api/clips" in script

async def test_an_unhashable_sensitivity_value_is_a_400_not_a_crash(client):
    """A list is not a name: it must be refused, not raise inside the lookup."""
    response = await client.post("/api/motion", json={"sensitivity": []})

    assert response.status == 400


async def test_a_non_ascii_frame_number_is_a_404(client):
    """Superscript digits pass ``str.isdigit`` but not ``int``; refuse them."""
    response = await client.get("/api/clips/20260101_120000/%C2%B2.jpg")

    assert response.status == 404