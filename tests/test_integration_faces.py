"""The face registry end to end: register, recognise, restart, forget.

Every test talks to a listening server -- an ``aiohttp`` AppRunner on a free
high port, or a real ``run_server.py`` process -- and asserts only on what a
client can see: HTTP bodies and the registry file on disk.  Only the MediaPipe
landmarker stands in, at the library boundary (``FaceRecognizer._detect``); the
pump, the encoder, the analysis tick, the embedding arithmetic, the distance
comparison, the registry lock, the atomic write and the HTTP layer all run.
``ServerProcess`` adopts the 02 gate's persistence probe (the ``--known-faces`` flag across a real restart).
"""

import asyncio
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import cv2
import numpy as np
import pytest
from aiohttp import web

from rvm.analysis import states
from rvm.analysis.gesture import GestureDetection
from rvm.analysis.recognition import EmotionDetection
from rvm.server.app import create_app
from rvm.server.session import StreamSession

# Same workaround as tests/test_face_api.py: OpenCV 4.14 aborts at exit after
# Haar ran on the encode worker thread.
cv2.ocl.setUseOpenCL(False)

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 160, 96

#: Three landmarks in the middle of the frame, so one face is nine values.
LANDMARK = SimpleNamespace(x=0.5, y=0.5, z=0.0)
ONE_FACE = SimpleNamespace(face_landmarks=[[LANDMARK, LANDMARK, LANDMARK]])
NO_FACE = SimpleNamespace(face_landmarks=[])

#: Hand-computed: (x, y, z) for three landmarks; every sampled frame yields it.
EMBEDDING = [0.5, 0.5, 0.0, 0.5, 0.5, 0.0, 0.5, 0.5, 0.0]

def build_session(tmp_path, known_faces, *, faces=True) -> StreamSession:
    """A session whose models are "ready" and whose landmarker is a stand-in."""
    session = StreamSession(
        width=WIDTH, height=HEIGHT, fps=15.0, bitrate=300_000,
        record_dir=tmp_path / "clips",
        # ``analysis=False`` only skips the warm-up thread that loads the three
        # real models; the analysis path itself is switched on below.
        analysis=False, analysis_interval=0.0, known_faces=known_faces,
    )
    session.analysis_enabled = True
    session._models_ready.set()
    session.face_recognizer._model = object()
    session.face_recognizer._detect = lambda frame: ONE_FACE if faces else NO_FACE
    session.emotion_recognizer.detect = lambda frame: EmotionDetection([], states.STATE_RUNNING)
    session.gesture_recognizer.detect = lambda frame: GestureDetection([], states.STATE_RUNNING)
    # ``features()`` (reached from every status read) asks each analyser whether
    # it is available, which would load a real model; the failure cache says no.
    for idle in (session.emotion_recognizer, session.gesture_recognizer): idle._failure = "stubbed"
    return session


async def wait_until(probe, description: str, timeout: float = 15.0):
    """Poll *probe* until it is truthy; running out of time is a real failure."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if asyncio.iscoroutine(value):
            value = await value
        if value:
            return value
        await asyncio.sleep(0.02)
    raise AssertionError(f"timed out after {timeout}s waiting for {description}")


class RunningServer:
    """The application under test, on a port, plus a client for it."""

    def __init__(self, session, http, base: str) -> None:
        self.session, self.http, self.base = session, http, base

    def url(self, path: str) -> str:
        return self.base + path

    async def json(self, path: str):
        response = await self.http.get(self.url(path))
        assert response.status == 200, f"GET {path} answered {response.status}"
        return await response.json()

    async def identities(self):
        return (await self.json("/api/faces/identities"))["identities"]

    async def wait_for_analysis(self, frames: int = 3, timeout: float = 15.0):
        await wait_until(lambda: len(self.session._recent_frames) >= frames,
                         f"{frames} analysed frames", timeout)

    async def wait_for_identity(self, name: str, timeout: float = 15.0):
        async def probe():
            for identity in await self.identities():
                if identity["name"] == name:
                    return identity
            return None

        return await wait_until(probe, f"{name!r} to be recognised", timeout)

    async def wait_for_no_identity(self, timeout: float = 15.0):
        async def probe():
            return not await self.identities()

        await wait_until(probe, "nobody to be recognised", timeout)


@asynccontextmanager
async def running_server(tmp_path, known_faces, *, faces=True):
    """Start the application on a free port, and stop it on the way out."""
    session = build_session(tmp_path, known_faces, faces=faces)
    runner = web.AppRunner(create_app(prefer_camera=False, session=session))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    port = runner.addresses[0][1]
    assert port > 1024, f"{port} is not a high random port"
    async with aiohttp.ClientSession() as http:
        try:
            yield RunningServer(session, http, f"http://127.0.0.1:{port}")
        finally:
            await runner.cleanup()


async def test_a_face_is_registered_recognised_across_a_restart_and_forgotten(tmp_path):
    """AS-1, AS-2 and AS-3 in one lifetime and one restart.

    The assertions that matter are the second server's: it never saw the
    registration, so it only shows the name by having read the file.
    """
    known = tmp_path / "data" / "known_faces.json"

    async with running_server(tmp_path, known) as first:
        await first.wait_for_analysis()
        response = await first.http.post(first.url("/api/faces/known"), json={"name": "Alice Ng"})
        assert response.status == 201
        assert await response.json() == {"name": "Alice Ng", "samples": 3, "known": ["Alice Ng"]}
        assert await first.json("/api/faces/known") == {"known": ["Alice Ng"]}
        identity = await first.wait_for_identity("Alice Ng")
        assert identity["confidence"] == 1.0
        assert json.loads(known.read_text(encoding="utf-8")) == {"version": 1, "faces": {"Alice Ng": EMBEDDING}}

    async with running_server(tmp_path, known) as second:
        identity = await second.wait_for_identity("Alice Ng")
        assert identity["confidence"] == 1.0
        response = await second.http.delete(second.url("/api/faces/known/Alice%20Ng"))
        assert response.status == 200
        assert await response.json() == {"removed": True, "known": []}
        await second.wait_for_no_identity()
        assert json.loads(known.read_text(encoding="utf-8"))["faces"] == {}
        assert (await second.http.get(second.url("/api/status"))).status == 200


async def test_a_refused_registration_leaves_the_file_alone_and_the_server_working(tmp_path):
    """AS-4: the two refusals a demo hits, and the server afterwards."""
    known = tmp_path / "data" / "known_faces.json"

    async with running_server(tmp_path, known) as server:
        await server.wait_for_analysis()
        first = await server.http.post(server.url("/api/faces/known"), json={"name": "Alice Ng"})
        assert first.status == 201
        before = known.read_bytes()

        duplicate = await server.http.post(server.url("/api/faces/known"), json={"name": "Alice Ng"})
        assert duplicate.status == 409
        assert (await duplicate.json())["reason"] == "name-exists"
        assert known.read_bytes() == before

        # Nobody in view: the landmarker answers with no faces at all.
        server.session.face_recognizer._detect = lambda frame: NO_FACE
        faceless = await server.http.post(server.url("/api/faces/known"), json={"name": "Bob"})
        assert faceless.status == 409
        assert (await faceless.json())["reason"] == "no-face"
        assert known.read_bytes() == before

        # Still a working server, not merely a working error handler.
        assert (await server.http.get(server.url("/api/status"))).status == 200
        assert await server.json("/api/faces/known") == {"known": ["Alice Ng"]}
        server.session.face_recognizer._detect = lambda frame: ONE_FACE
        retried = await server.http.post(server.url("/api/faces/known"), json={"name": "Bob"})
        assert retried.status == 201
        assert await server.json("/api/faces/known") == {"known": ["Alice Ng", "Bob"]}


class ServerProcess:
    """A real ``run_server.py`` on a free high port, driven over HTTP."""

    def __init__(self, tmp_path, known_faces) -> None:
        self.tmp_path, self.known_faces = tmp_path, known_faces
        self.base, self.process, self.output = "", None, ""

    def __enter__(self) -> "ServerProcess":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        assert port > 1024, f"{port} is not a high random port"
        self.base = f"http://127.0.0.1:{port}"
        # ``--no-analysis`` keeps the three real models out of the test: the
        # seams here are the flag, the file and the process boundary.
        self.process = subprocess.Popen(
            [sys.executable, str(REPO_ROOT / "run_server.py"), "--no-camera",
             "--no-analysis", "--port", str(port),
             "--known-faces", str(self.known_faces), "--recordings", str(self.tmp_path / "clips")],
            cwd=str(REPO_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(
                    "run_server.py exited before it served: " + self.process.stdout.read()[-1500:]
                )
            try:
                urllib.request.urlopen(self.base + "/api/status", timeout=2.0).read()
                return self
            except Exception:  # noqa: BLE001 - the server is still starting
                time.sleep(0.1)
        raise AssertionError(f"run_server.py never answered on {self.base}")

    def __exit__(self, *exc_info) -> bool:
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.output, _ = self.process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.output, _ = self.process.communicate(timeout=15)
        return False

    def request(self, method: str, path: str, payload=None, timeout: float = 10.0):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def known(self):
        return self.request("GET", "/api/faces/known")[1]


@pytest.mark.slow
def test_real_processes_carry_the_registry_and_survive_a_corrupt_one(tmp_path):
    """Adopted from ``verifier-probes/02-r2-verifier-persist.py``.

    Phase one: nothing in the suite started ``run_server.py``, so "``--known-
    faces`` reaches the store" and "a second process reads the list the first one wrote" were both unproven.
    The third process is what makes the deletion a persistence claim rather than a response claim.
    Phase two: two entries of different widths are one file spliced together by
    hand, which the store calls corrupt; a real process is the only way to show
    the warning is logged and the pump keeps running.
    """
    registry = tmp_path / "data" / "known_faces.json"
    registry.parent.mkdir(parents=True)
    # Hand-written: two names at a width nothing here has to match.
    registry.write_text(json.dumps({"version": 1, "faces": {"Alice Ng": [0.25, 0.5], "Bob": [0.75, 0.5]}}), encoding="utf-8")

    with ServerProcess(tmp_path, registry) as first:
        assert first.known() == {"known": ["Alice Ng", "Bob"]}

    with ServerProcess(tmp_path, registry) as second:
        assert second.known() == {"known": ["Alice Ng", "Bob"]}
        status, body = second.request("DELETE", "/api/faces/known/Bob")
        assert status == 200
        assert body == {"removed": True, "known": ["Alice Ng"]}
        assert json.loads(registry.read_text(encoding="utf-8"))["faces"] == {"Alice Ng": [0.25, 0.5]}

    with ServerProcess(tmp_path, registry) as third:
        assert third.known() == {"known": ["Alice Ng"]}

    broken = tmp_path / "broken" / "known_faces.json"
    broken.parent.mkdir()
    broken.write_text(json.dumps({"version": 1, "faces": {"Alice": [0.5, 0.25], "Bob": [0.5, 0.25, 0.125]}}), encoding="utf-8")

    with ServerProcess(tmp_path, broken) as degraded:
        assert degraded.known() == {"known": []}
        deadline = time.monotonic() + 15.0
        while degraded.request("GET", "/api/status")[1]["frames"] < 1:
            assert time.monotonic() < deadline, "the picture pump is not running"
            time.sleep(0.05)
        status, body = degraded.request("GET", "/api/status")
        assert status == 200
        assert body["source"] == "synthetic"

    assert "corrupt" in degraded.output.lower(), degraded.output[-500:]
