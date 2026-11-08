# Verifier probe (08 r1, v2): name validation at POST /api/faces/known.
# Standalone -- replicates the test fixture pattern (stubbed analysers, real
# HTTP layer via aiohttp TestClient) but written independently; NOT part of the
# shipped suite. Usage: python 08-r1-name-validation-probe-v2.py <worktree>
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, sys.argv[1] + "\\src")
from rvm.analysis import states  # noqa: E402
from rvm.analysis.emotion import EmotionDetection  # noqa: E402
from rvm.analysis.gesture import GestureDetection  # noqa: E402
from rvm.analysis.recognition import FaceRecognition  # noqa: E402
from rvm.server.app import create_app  # noqa: E402
from rvm.server.session import StreamSession  # noqa: E402

cv2.ocl.setUseOpenCL(False)

HOSTILE = [
    ".", "..", " . ", "../x", "a/b", "a\\b", "/etc/passwd",
    "tab\there", "nul\x00byte", "del\x7fchar",
    "   ", "\t\n", "", "x" * 41,
]
LEGAL = ["Alice Ng", "张小英", "O'Brien", "Zoë", "  Mary Ann  ", "a..b", "..a", "a%2Fb"]

W, H = 160, 96


def make_session(tmp):
    s = StreamSession(
        width=W, height=H, fps=10.0, bitrate=300_000,
        record_dir=tmp / "clips", analysis=False,
        analysis_interval=0.0, known_faces=tmp / "data" / "known_faces.json",
    )
    s.analysis_enabled = True
    s._models_ready.set()
    s.face_recognizer.recognize = lambda f: FaceRecognition([], states.STATE_RUNNING)
    s.emotion_recognizer.detect = lambda f: EmotionDetection([], states.STATE_RUNNING)
    s.gesture_recognizer.detect = lambda f: GestureDetection([], states.STATE_RUNNING)
    s.face_recognizer.sample_faces = lambda f: [np.array([float(f[0, 0, 0])])]
    return s


async def feed(session, v):
    session.inject_frame(np.full((H, W, 3), v, dtype=np.uint8))
    await session.run_once()


async def main():
    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        session = make_session(tmp)
        app = create_app(session=session)
        app.on_startup.clear()
        client = TestClient(TestServer(app))
        await client.start_server()
        faces_file = tmp / "data" / "known_faces.json"

        for v in (10, 20, 30):
            await feed(session, v)

        for name in HOSTILE:
            r = await client.post("/api/faces/known", json={"name": name})
            body = await r.json()
            ok = (r.status == 400 and body.get("reason") == "bad-name"
                  and not faces_file.exists())
            results.append(("HOSTILE", repr(name), r.status,
                            body.get("reason"), not faces_file.exists(), ok))

        for name in LEGAL:
            r = await client.post("/api/faces/known", json={"name": name})
            body = await r.json()
            stored = (json.loads(faces_file.read_text("utf-8"))["faces"]
                      if faces_file.exists() else {})
            d = await client.delete("/api/faces/known/" + quote(name.strip(), safe=""))
            ok = (r.status == 201 and list(stored) == [name.strip()]
                  and d.status == 200)
            results.append(("LEGAL", repr(name), r.status,
                            body.get("reason", "-"), d.status, ok))

        gl = await client.get("/api/faces/known")
        known = (await gl.json())["known"]
        results.append(("LIST", "known=" + json.dumps(known, ensure_ascii=False),
                        gl.status, "-", known == [], known == []))

        await client.close()
        session.close()

    bad = [r for r in results if not r[5]]
    for kind, name, st, reason, extra, ok in results:
        print(f"{'OK ' if ok else 'FAIL'} {kind:7} {name:26} status={st} "
              f"reason={reason} extra={extra}")
    print(f"RESULT: {len(results) - len(bad)}/{len(results)} pass; "
          f"{'ALL GREEN' if not bad else 'FAILURES'}")
    sys.exit(1 if bad else 0)


asyncio.run(main())
