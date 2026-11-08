#!/usr/bin/env python3
"""Independent r1 verifier probe for ticket 05.

Re-derives the four-step chain and the failure path against a REAL listening
server (aiohttp AppRunner on a free OS port), with my own driver. Only the
MediaPipe landmarker is stubbed at the library boundary (``_detect``); HTTP,
analysis tick, embedding mean, distance, lock, atomic save and restart reload
all run for real. Prints evidence lines for the .md record.

Run inside the gate worktree:
    <venv-python> 05-integration-verifier.py
"""

import asyncio
import json
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent / "src")) if (Path(__file__).resolve().parent / "src").exists() else None

import aiohttp
import cv2
import numpy as np
from aiohttp import web

# Same workaround as tests/test_face_api.py: OpenCV 4.14 aborts at exit after
# Haar ran on the encode worker thread (session._analyse calls face_detector).
cv2.ocl.setUseOpenCL(False)

from rvm.analysis import states
from rvm.analysis.gesture import GestureDetection
from rvm.analysis.recognition import EmotionDetection
from rvm.server.app import create_app
from rvm.server.session import StreamSession

LANDMARK = SimpleNamespace(x=0.5, y=0.5, z=0.0)
ONE_FACE = SimpleNamespace(face_landmarks=[[LANDMARK, LANDMARK, LANDMARK]])
NO_FACE = SimpleNamespace(face_landmarks=[])

evidence = []


def ev(line):
    print(line)
    evidence.append(line)


def make_session(tmp, known, faces=True):
    s = StreamSession(
        width=160, height=96, fps=15.0, bitrate=300_000,
        record_dir=tmp / "clips",
        analysis=False, analysis_interval=0.0, known_faces=known,
    )
    s.analysis_enabled = True
    s._models_ready.set()
    s.face_recognizer._model = object()
    s.face_recognizer._detect = lambda frame: ONE_FACE if faces else NO_FACE
    s.emotion_recognizer.detect = lambda f: EmotionDetection([], states.STATE_RUNNING)
    s.gesture_recognizer.detect = lambda f: GestureDetection([], states.STATE_RUNNING)
    for idle in (s.emotion_recognizer, s.gesture_recognizer):
        idle._failure = "stubbed"
    return s


async def start(tmp, known, faces=True):
    session = make_session(tmp, known, faces)
    runner = web.AppRunner(create_app(prefer_camera=False, session=session))
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    host, port = runner.addresses[0]
    # Independently prove a real socket is listening (not a mock transport).
    probe = socket.create_connection((host, port), timeout=2)
    peer = probe.getpeername()
    probe.close()
    ev(f"LISTENING {host}:{port} (peer {peer}, port>1024={port > 1024})")
    return session, runner, f"http://{host}:{port}"


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="v05-chain-"))
    known = tmp / "data" / "known_faces.json"
    ev(f"TMP {tmp}")

    async with aiohttp.ClientSession() as http:
        # ---- instance 1: register -> identify ----
        session, runner, base = await start(tmp, known)
        await asyncio.sleep(0.5)  # let the analysis tick collect >=3 frames
        async with http.post(base + "/api/faces/known", json={"name": "Carol Wu"}) as r:
            body = await r.json()
            ev(f"STEP1 register status={r.status} body={body}")
        for _ in range(200):
            async with http.get(base + "/api/faces/identities") as r:
                ids = (await r.json())["identities"]
            if any(i["name"] == "Carol Wu" for i in ids):
                break
            await asyncio.sleep(0.05)
        ev(f"STEP2 identities={ids}")
        ev(f"FILE1 {known.read_text(encoding='utf-8')}")
        await runner.cleanup()

        # ---- instance 2 (restart): still identifies, then delete ----
        session2, runner2, base2 = await start(tmp, known)
        for _ in range(200):
            async with http.get(base2 + "/api/faces/identities") as r:
                ids2 = (await r.json())["identities"]
            if any(i["name"] == "Carol Wu" for i in ids2):
                break
            await asyncio.sleep(0.05)
        ev(f"STEP3 after-restart identities={ids2}")
        async with http.delete(base2 + "/api/faces/known/Carol%20Wu") as r:
            ev(f"STEP4 delete status={r.status} body={await r.json()}")
        ev(f"FILE2 {known.read_text(encoding='utf-8')}")
        await asyncio.sleep(0.5)
        async with http.get(base2 + "/api/faces/identities") as r:
            ev(f"POST-DELETE identities={(await r.json())['identities']}")
        async with http.get(base2 + "/api/status") as r:
            ev(f"POST-DELETE /api/status={r.status}")
        await runner2.cleanup()

        # ---- instance 3: failure path then still works ----
        session3, runner3, base3 = await start(tmp, known, faces=True)
        await asyncio.sleep(0.5)
        async with http.post(base3 + "/api/faces/known", json={"name": "Dan"}) as r:
            ev(f"FAILPATH seed register status={r.status}")
        before = known.read_bytes()
        async with http.post(base3 + "/api/faces/known", json={"name": "Dan"}) as r:
            ev(f"FAILPATH duplicate status={r.status} body={await r.json()}")
        ev(f"FAILPATH file-unchanged={known.read_bytes() == before}")
        session3.face_recognizer._detect = lambda f: NO_FACE
        async with http.post(base3 + "/api/faces/known", json={"name": "Eve"}) as r:
            ev(f"FAILPATH no-face status={r.status} body={await r.json()}")
        ev(f"FAILPATH file-unchanged={known.read_bytes() == before}")
        async with http.get(base3 + "/api/status") as r:
            ev(f"FAILPATH /api/status={r.status}")
        session3.face_recognizer._detect = lambda f: ONE_FACE
        async with http.post(base3 + "/api/faces/known", json={"name": "Eve"}) as r:
            ev(f"FAILPATH retry status={r.status} body={await r.json()}")
        await runner3.cleanup()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
