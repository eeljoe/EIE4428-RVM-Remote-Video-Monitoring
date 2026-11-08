"""The face registry endpoints, and the thread discipline behind them.

The interface contract fixes the shapes these tests pin: ``201`` with
``{"name","samples","known"}``, ``{"known": [...]}``, ``{"removed": true,
"known": [...]}``, and failures as ``{"error", "reason"}`` with the enumerated
reason.  MediaPipe itself is stubbed at the library boundary -- a model
inference is not what this ticket owns -- while the averaging, the lock, the
store and the HTTP layer all run for real.
"""

import asyncio
import json
import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from aiohttp.test_utils import TestClient, TestServer

from rvm.analysis import states
from rvm.analysis.face_store import DEFAULT_KNOWN_FACES
from rvm.analysis.gesture import GestureDetection
from rvm.analysis.recognition import (
    EmotionDetection,
    FaceRecognition,
    FaceSamplingError,
)
from rvm.server.app import SESSION, create_app
from rvm.server.session import StreamSession

#: The reasons the interface contract allows, and all of them.
CONTRACT_REASONS = {
    "bad-name",
    "name-exists",
    "no-face",
    "multiple-faces",
    "samples-missing",
    "analysis-disabled",
    "models-loading",
    "unavailable",
    "write-failed",
}

WIDTH, HEIGHT = 160, 96

#: OpenCV 4.14 initialises an OpenCL device when the Haar cascade runs outside
#: the main thread -- which is where the encode pipeline runs it -- and then
#: fails to release that device at process exit: ``CL_INVALID_OPERATION during
#: clReleaseDevice`` aborts the interpreter *after* every test has passed.  A
#: probe that only calls ``FaceDetector().detect`` from a worker thread
#: reproduces it without a line of this ticket's code.  Nothing here needs the
#: GPU path, so it is switched off for the test process; the product is left
#: alone.
cv2.ocl.setUseOpenCL(False)


def assert_contract(body: dict) -> None:
    assert set(body) == {"error", "reason"}
    assert body["reason"] in CONTRACT_REASONS, body["reason"]
    assert isinstance(body["error"], str) and body["error"]


def stub_analysers(session: StreamSession) -> None:
    """Replace the three model calls with cheap stand-ins.

    ``recognize``/``detect``/``sample_faces`` are the only places a MediaPipe
    model runs; standing them in keeps the analysis tick honest (it still
    counts as one inference section) without paying seconds of model loading
    per test.
    """
    session.face_recognizer.recognize = lambda frame: FaceRecognition(
        [], states.STATE_RUNNING
    )
    session.emotion_recognizer.detect = lambda frame: EmotionDetection(
        [], states.STATE_RUNNING
    )
    session.gesture_recognizer.detect = lambda frame: GestureDetection(
        [], states.STATE_RUNNING
    )
    session.face_recognizer.sample_faces = lambda frame: [
        np.array([float(frame[0, 0, 0])])
    ]


def make_session(
    tmp_path,
    *,
    analysis: bool = True,
    known_faces=None,
    real_face_recognition: bool = False,
) -> StreamSession:
    """A session with "models ready" already true and the models stubbed."""
    path = known_faces if known_faces is not None else tmp_path / "data" / "known_faces.json"
    session = StreamSession(
        width=WIDTH,
        height=HEIGHT,
        fps=10.0,
        bitrate=300_000,
        record_dir=tmp_path / "clips",
        # The warm-up thread is what ``analysis=True`` starts, and it loads
        # three models; the state it ends in is all these tests need.
        analysis=False,
        analysis_interval=0.0,
        known_faces=path,
    )
    if analysis:
        session.analysis_enabled = True
        session._models_ready.set()
    stub_analysers(session)
    if real_face_recognition:
        # ``stub_analysers`` shadows the method with an instance attribute;
        # dropping the shadow brings back the real identify path, so the
        # distance arithmetic against the registry runs for real.
        del session.face_recognizer.recognize
    return session


@pytest.fixture
async def build(tmp_path):
    """Start one app per request, and close everything afterwards."""
    started: list[tuple[TestClient, StreamSession]] = []

    async def factory(*, analysis: bool = True, known_faces=None, real_face_recognition=False):
        session = make_session(
            tmp_path,
            analysis=analysis,
            known_faces=known_faces,
            real_face_recognition=real_face_recognition,
        )
        app = create_app(session=session)
        # These tests push pictures one at a time with ``feed``; the background
        # pump would race them for the retained frames and make "the last three
        # analysed frames" mean "whatever the generator produced meanwhile".
        app.on_startup.clear()
        client = TestClient(TestServer(app))
        await client.start_server()
        started.append((client, session))
        return session, client

    yield factory
    for client, session in started:
        await client.close()
        session.close()


async def feed(session: StreamSession, value: int) -> None:
    """Push one picture through the real encode/analysis path."""
    session.inject_frame(np.full((HEIGHT, WIDTH, 3), value, dtype=np.uint8))
    await session.run_once()


async def feed_three(session: StreamSession, values=(10, 20, 30)) -> None:
    for value in values:
        await feed(session, value)


def list_file(tmp_path):
    return tmp_path / "data" / "known_faces.json"


# --------------------------------------------------------------------------
# Registering
# --------------------------------------------------------------------------


async def test_registering_a_face_averages_the_last_three_analysed_frames(build, tmp_path):
    session, client = await build()
    # Four analysed frames: the oldest must not influence the sample.
    await feed_three(session, values=(5, 10, 20, 30))

    response = await client.post("/api/faces/known", json={"name": "Alice Ng"})

    assert response.status == 201
    assert await response.json() == {
        "name": "Alice Ng",
        "samples": 3,
        "known": ["Alice Ng"],
    }
    stored = json.loads(list_file(tmp_path).read_text(encoding="utf-8"))
    # Hand-computed: one sample per frame, frames 10/20/30, mean is 20.
    assert stored["faces"] == {"Alice Ng": [20.0]}


async def test_registering_before_three_analysed_frames_is_refused(build, tmp_path):
    session, client = await build()
    await feed_three(session, values=(10, 20))

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 409
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "samples-missing"
    assert not list_file(tmp_path).exists()


async def test_registering_without_a_face_is_refused(build, tmp_path):
    session, client = await build()
    session.face_recognizer.sample_faces = lambda frame: []
    await feed_three(session)

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 409
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "no-face"
    assert not list_file(tmp_path).exists()


async def test_registering_with_two_faces_in_view_is_refused(build, tmp_path):
    session, client = await build()
    session.face_recognizer.sample_faces = lambda frame: [np.zeros(4), np.ones(4)]
    await feed_three(session)

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 409
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "multiple-faces"
    assert not list_file(tmp_path).exists()


async def test_a_duplicate_name_is_refused_and_the_file_is_untouched(build, tmp_path):
    session, client = await build()
    await feed_three(session)
    assert (await client.post("/api/faces/known", json={"name": "Alice"})).status == 201
    before = list_file(tmp_path).read_bytes()
    await feed_three(session, values=(40, 50, 60))

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 409
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "name-exists"
    assert list_file(tmp_path).read_bytes() == before


async def test_two_registrations_of_one_name_leave_one_entry(build, tmp_path):
    """Two operators (or two clicks) must not both get a 201 for one name.

    The duplicate check happens before three inferences, which is long enough
    for a second request with the same name to pass the same check.  The
    sample is slowed down here only to widen that window to something a test
    can rely on; the race itself is the product's.
    """
    session, client = await build()
    await feed_three(session)

    def slow(frame):
        time.sleep(0.05)
        return [np.array([float(frame[0, 0, 0])])]

    session.face_recognizer.sample_faces = slow

    first, second = await asyncio.gather(
        client.post("/api/faces/known", json={"name": "Alice"}),
        client.post("/api/faces/known", json={"name": "Alice"}),
    )

    assert sorted([first.status, second.status]) == [201, 409]
    refused = first if first.status == 409 else second
    body = await refused.json()
    assert_contract(body)
    assert body["reason"] == "name-exists"
    # Hand-computed: frames 10/20/30, one sample each, mean 20.
    stored = json.loads(list_file(tmp_path).read_text(encoding="utf-8"))
    assert stored["faces"] == {"Alice": [20.0]}
    assert (await (await client.get("/api/faces/known")).json()) == {"known": ["Alice"]}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "   "},
        {"name": 42},
        {"name": "x" * 41},
        {"name": "two\nlines"},
        {},
    ],
)
async def test_a_useable_name_is_required(build, tmp_path, payload):
    session, client = await build()
    await feed_three(session)

    response = await client.post("/api/faces/known", json=payload)

    assert response.status == 400
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "bad-name"
    assert not list_file(tmp_path).exists()


async def test_a_body_that_is_not_json_is_refused(build, tmp_path):
    _, client = await build()

    response = await client.post("/api/faces/known", data="not json")

    assert response.status == 400
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "bad-name"


# --------------------------------------------------------------------------
# Refusals that are about the installation, not the request
# --------------------------------------------------------------------------


async def test_registering_with_analysis_switched_off_is_refused(build, tmp_path):
    _, client = await build(analysis=False)

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 503
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "analysis-disabled"
    assert not list_file(tmp_path).exists()


async def test_registering_while_the_models_load_is_refused(build, tmp_path):
    session, client = await build()
    session._models_ready.clear()
    await feed_three(session)

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 503
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "models-loading"
    assert not list_file(tmp_path).exists()


async def test_an_unavailable_recogniser_is_reported_as_unavailable(build, tmp_path):
    session, client = await build()

    def broken(frame):
        raise FaceSamplingError("MediaPipe is not installed")

    session.face_recognizer.sample_faces = broken
    await feed_three(session)

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 503
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "unavailable"
    assert not list_file(tmp_path).exists()


# --------------------------------------------------------------------------
# Reading, deleting and surviving a failed write
# --------------------------------------------------------------------------


async def test_the_known_list_is_served_in_order(build, tmp_path):
    session, client = await build()
    await feed_three(session)
    assert (await client.post("/api/faces/known", json={"name": "Zoe"})).status == 201
    assert (await client.post("/api/faces/known", json={"name": "Alice Ng"})).status == 201

    response = await client.get("/api/faces/known")

    assert response.status == 200
    assert await response.json() == {"known": ["Alice Ng", "Zoe"]}


async def test_deleting_a_face_removes_it_and_writes_immediately(build, tmp_path):
    session, client = await build()
    await feed_three(session)
    assert (await client.post("/api/faces/known", json={"name": "Alice Ng"})).status == 201

    response = await client.delete("/api/faces/known/Alice%20Ng")

    assert response.status == 200
    assert await response.json() == {"removed": True, "known": []}
    stored = json.loads(list_file(tmp_path).read_text(encoding="utf-8"))
    assert stored["faces"] == {}
    assert (await client.get("/api/faces/known")).status == 200


async def test_deleting_a_name_that_is_not_registered_is_a_404(build):
    _, client = await build()

    response = await client.delete("/api/faces/known/Nobody")

    assert response.status == 404
    assert_contract(await response.json())


async def test_a_failed_write_is_reported_and_the_list_is_unchanged(build, tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file, so the registry cannot be written beside it", encoding="utf-8")
    session, client = await build(known_faces=blocker / "known_faces.json")
    await feed_three(session)

    response = await client.post("/api/faces/known", json={"name": "Alice"})

    assert response.status == 500
    body = await response.json()
    assert_contract(body)
    assert body["reason"] == "write-failed"
    assert (await client.get("/api/faces/known")).status == 200
    assert (await (await client.get("/api/faces/known")).json()) == {"known": []}


async def test_a_restart_loads_the_registered_faces(build, tmp_path):
    session, client = await build()
    await feed_three(session)
    assert (await client.post("/api/faces/known", json={"name": "Alice Ng"})).status == 201

    restarted = make_session(tmp_path, analysis=False)
    try:
        assert restarted.known_face_names() == ["Alice Ng"]
        # The vector is loaded, not merely the name: recognition has something
        # to compare against after a restart.
        assert restarted.face_recognizer.known_faces["Alice Ng"].tolist() == [20.0]
    finally:
        restarted.close()


# --------------------------------------------------------------------------
# The event loop and the inference lock
# --------------------------------------------------------------------------


async def test_registration_does_not_block_the_event_loop(build, tmp_path):
    session, client = await build()
    await feed_three(session)

    def slow(frame):
        time.sleep(0.2)  # 3 frames -> 0.6 s of "inference"
        return [np.array([float(frame[0, 0, 0])])]

    session.face_recognizer.sample_faces = slow

    posting = asyncio.create_task(client.post("/api/faces/known", json={"name": "Alice"}))
    ticks = 0
    deadline = time.monotonic() + 5.0
    while not posting.done() and time.monotonic() < deadline:
        await asyncio.sleep(0.02)
        ticks += 1
    response = await posting

    assert response.status == 201
    # A blocking handler would starve this loop: 0.6 s of inference against a
    # 0.02 s tick is ~30 turns if the work is on a thread, and about none if it
    # is on the loop.
    assert ticks >= 10, f"the loop only turned {ticks} times during the request"


async def test_status_and_snapshot_stay_available_while_registering(build, tmp_path):
    session, client = await build()
    await feed_three(session)

    def slow(frame):
        time.sleep(0.15)
        return [np.array([float(frame[0, 0, 0])])]

    session.face_recognizer.sample_faces = slow
    posting = asyncio.create_task(client.post("/api/faces/known", json={"name": "Alice"}))
    await asyncio.sleep(0.1)

    assert not posting.done(), "the request finished too fast to prove anything"
    status = await client.get("/api/status")
    snapshot = await client.get("/api/snapshot.jpg")

    assert status.status == 200
    assert (await status.json())["frames"] >= 3
    assert snapshot.status == 200
    assert (await posting).status == 201


async def test_registration_and_analysis_take_the_same_lock(build, tmp_path):
    session, client = await build()
    await feed_three(session)
    assert session._inference_lock.acquire(blocking=False) is True
    try:
        posting = asyncio.create_task(
            client.post("/api/faces/known", json={"name": "Alice"})
        )
        session.inject_frame(np.full((HEIGHT, WIDTH, 3), 40, dtype=np.uint8))
        analysing = asyncio.create_task(session.run_once())
        await asyncio.sleep(0.3)

        assert not posting.done(), "registration must wait for the inference lock"
        assert not analysing.done(), "analysis must wait for the same lock"
    finally:
        session._inference_lock.release()

    assert (await posting).status == 201
    await analysing


# --------------------------------------------------------------------------
# The registry and the recogniser are one list
# --------------------------------------------------------------------------


def registering_session(tmp_path) -> StreamSession:
    """A session whose landmarker answers with one fixed sample per frame."""
    session = make_session(tmp_path)
    session._recent_frames = [
        np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8) for _ in range(3)
    ]
    # Hand-given: every sample is the same vector, so the average is that
    # vector -- the arithmetic is pinned exactly, not approximately.
    session.face_recognizer.sample_faces = lambda frame: [np.full(8, 2.0)]
    return session


def test_registering_updates_the_recogniser_mirror_immediately(tmp_path):
    """"Register a face and it works at once" is the whole demo.

    ``_publish_faces`` writes the file and updates the store; the recogniser
    keeps its own copy so that identifying a picture costs no file access.
    Leaving that copy stale is invisible in the response (201, correct file,
    correct store) and shows up only when the face just registered is not
    recognised until the server is restarted.
    """
    session = registering_session(tmp_path)
    try:
        session.register_face("Ada")

        assert set(session.face_recognizer.known_faces) == {"Ada"}
        assert np.allclose(session.face_recognizer.known_faces["Ada"], np.full(8, 2.0))
    finally:
        session.close()


def test_deleting_updates_the_recogniser_mirror_immediately(tmp_path):
    """A deleted face must stop matching, not linger until a restart."""
    session = registering_session(tmp_path)
    try:
        session.register_face("Ada")
        session.register_face("Bob")

        session.remove_face("Ada")

        assert set(session.face_recognizer.known_faces) == {"Bob"}
    finally:
        session.close()


def test_the_store_and_the_recogniser_agree_after_every_change(tmp_path):
    session = registering_session(tmp_path)
    try:
        for name in ("Ada", "Bob", "Carol"):
            session.register_face(name)
            assert set(session.face_recognizer.known_faces) == set(
                session.face_store.faces
            )

        session.remove_face("Bob")

        assert set(session.face_recognizer.known_faces) == set(session.face_store.faces)
        assert set(session.face_recognizer.known_faces) == {"Ada", "Carol"}
    finally:
        session.close()


# --------------------------------------------------------------------------
# A registry that does not line up with the model
# --------------------------------------------------------------------------


async def test_a_hand_written_list_of_the_wrong_width_does_not_stop_the_stream(
    build, tmp_path
):
    """A stale registry must not take the picture stream down with it.

    ``embedding - registered`` raises ``ValueError`` when the widths differ,
    and nothing between ``_analyse`` and the pump task catches it: one entry
    from an older landmarker (or one typed by hand) stops the stream for good.
    The honest reading is that such an entry cannot match.
    """
    registry = list_file(tmp_path)
    registry.parent.mkdir(parents=True, exist_ok=True)
    # Eight values per face: real embeddings here are three per landmark.
    registry.write_text(
        json.dumps({"version": 1, "faces": {"Bob": [0.75] * 8}}), encoding="utf-8"
    )
    session, client = await build(real_face_recognition=True)
    # The landmarker is stubbed at the library boundary; the registry, the
    # distance arithmetic, the analysis tick and the pump task all run.
    session.face_recognizer._model = object()
    session.face_recognizer._detect = lambda frame: SimpleNamespace(
        face_landmarks=[[SimpleNamespace(x=0.5, y=0.5, z=0.0)] * 3]
    )
    session.fps = 50.0

    stop = asyncio.Event()
    pump = asyncio.create_task(session.run_forever(stop))
    try:
        # Feed pictures until one is through the pipeline: the first analysis
        # tick is what compares the face with the stale entry, and a tick that
        # raises takes the task (and the stream) with it.
        value = 0
        deadline = time.monotonic() + 5.0
        while session._frames < 1 and not pump.done() and time.monotonic() < deadline:
            value += 1
            session.inject_frame(
                np.full((HEIGHT, WIDTH, 3), 10 + value, dtype=np.uint8)
            )
            await asyncio.sleep(0.02)

        assert not pump.done(), f"the picture pump stopped: {pump.exception()!r}"
        assert session._frames >= 1, "no picture was encoded"
        assert (await client.get("/api/status")).status == 200
        # Nothing matched -- a wrong-width entry cannot be a name for a face.
        assert session.face_recognizer.known_faces["Bob"].shape == (8,)
    finally:
        stop.set()
        if pump.done():
            pump.exception()  # reported by the assertion above; do not re-raise
        else:
            await asyncio.wait_for(pump, timeout=5.0)


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


def test_the_registry_path_reaches_the_session(tmp_path):
    path = tmp_path / "registry" / "faces.json"
    app = create_app(prefer_camera=False, known_faces=path)
    session: StreamSession = app[SESSION]
    try:
        assert session.face_store.path == path
    finally:
        session.close()


def test_the_default_registry_path_is_the_data_directory():
    app = create_app(prefer_camera=False)
    session: StreamSession = app[SESSION]
    try:
        assert session.face_store.path == DEFAULT_KNOWN_FACES
    finally:
        session.close()
