#!/usr/bin/env python3
"""overall-dynamic gate launcher: real server, stubbed landmarker boundary.

A synthetic scene contains no real faces, so the two places where the product
touches MediaPipe landmarks are replaced at the class boundary:

- ``FaceRecognizer.sample_faces``  returns N constant embeddings per frame
  (or raises ``FaceSamplingError``), controlled live by a JSON file;
- ``FaceRecognizer.recognize``     returns a ``FaceRecognition`` built from
  the same file, or ``"real"`` to pass through to the real implementation.

Everything else is the real product: warmup, the models-ready gate, the
three-frame averaging, the name checks, the file write, the mirror publish,
the HTTP layer, and the whole page.  The control file is re-read per call so
one server can play several scenes without a restart.

    set OD_STUB_CTL=C:\\path\\ctl.json
    python overall-dynamic-stub-server.py --port 8150 --known-faces data\\known_faces.json

ctl.json keys::

    {"sample_n": 1}                 one face per frame (registration succeeds)
    {"sample_n": 2}                 two faces -> 409 multiple-faces
    {"sample_n": 0}                 no face   -> 409 no-face
    {"sample_n": "raise"}           FaceSamplingError -> 503 unavailable
    {"sample_n": "real"}            real landmarker
    {"sample_delay": 0.25}          seconds slept inside each sampling call
    {"recognize": "real"}           real recognise() pass-through
    {"recognize": {"state": "running", "seen": 1,
                   "identities": [["Gate Person", 0.971]]}}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))

from aiohttp import web  # noqa: E402

from rvm.analysis.recognition import (  # noqa: E402
    FaceRecognition,
    FaceRecognizer,
    FaceSamplingError,
)
from rvm.server.app import create_app  # noqa: E402

_orig_sample = FaceRecognizer.sample_faces
_orig_recognize = FaceRecognizer.recognize

#: A constant 1434-dim vector, the width a real landmarker returns.
_EMB = np.linspace(0.0, 1.0, 1434)


def _ctl() -> dict:
    path = os.environ.get("OD_STUB_CTL")
    if path:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a bad probe file must not kill the stream
            pass
    return {}


def _sample(self, frame):
    n = _ctl().get("sample_n", "real")
    if n == "real":
        return _orig_sample(self, frame)
    if n == "raise":
        raise FaceSamplingError("stub landmarker failure (overall-dynamic gate)")
    delay = float(_ctl().get("sample_delay", 0) or 0)
    if delay:
        time.sleep(delay)
    return [_EMB.copy() for _ in range(int(n))]


def _recognize(self, frame):
    spec = _ctl().get("recognize", "real")
    if spec == "real":
        return _orig_recognize(self, frame)
    ids = [
        (name, float(conf), (4, 8, 60, 60))
        for name, conf in spec.get("identities", [])
    ]
    return FaceRecognition(ids, spec.get("state", "running"), int(spec.get("seen", 1)))


FaceRecognizer.sample_faces = _sample
FaceRecognizer.recognize = _recognize


def main() -> None:
    parser = argparse.ArgumentParser(description="overall-dynamic stub server")
    parser.add_argument("--port", type=int, default=8150)
    parser.add_argument("--known-faces", default="data/known_faces.json")
    parser.add_argument("--recordings", default="recordings")
    parser.add_argument("--interval", type=float, default=0.05)
    args = parser.parse_args()

    async def serve() -> None:
        app = create_app(
            prefer_camera=False,
            record_dir=args.recordings,
            analysis=True,
            analysis_interval=args.interval,
            known_faces=args.known_faces,
        )
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", args.port)
        await site.start()
        print(
            f"STUB-RVM serving on http://127.0.0.1:{args.port}/ "
            f"(sample_faces/recognize stubbed via OD_STUB_CTL)",
            flush=True,
        )
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await runner.cleanup()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
