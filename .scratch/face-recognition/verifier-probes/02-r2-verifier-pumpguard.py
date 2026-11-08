#!/usr/bin/env python3
"""Independent r2 verifier probe: a wrong-width registry must not kill the pump.

Drives a REAL ``StreamSession.run_forever`` pump task with a uniform
wrong-width registry loaded from disk ({'Odd': 8 values}) and a stubbed
landmarker that yields real 3-landmark detections (9-dim embeddings).  The
analysis tick's distance arithmetic runs for real -- under HEAD the wrong-width
entry is skipped and the pump keeps encoding; with the ``_nearest`` guard
removed the ``ValueError`` travels out of ``_analyse`` and the task dies.

    python 02-r2-verifier-pumpguard.py          # expect PUMP ALIVE at HEAD
    python 02-r2-verifier-pumpguard.py --expect-dead   # under the mutant

Env: VERIFY_WT (verification worktree, required).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

WORKTREE = Path(os.environ["VERIFY_WT"])
sys.path.insert(0, str(WORKTREE / "src"))

try:
    import cv2
    cv2.ocl.setUseOpenCL(False)
except Exception:  # noqa: BLE001
    pass

from rvm.server.session import StreamSession  # noqa: E402

W, H = 320, 240


async def run() -> int:
    expect_dead = "--expect-dead" in sys.argv
    tmp = Path(tempfile.mkdtemp(prefix="v02r2pump-"))
    registry = tmp / "known_faces.json"
    # One hand-written 8-value entry: uniform width, so _parse accepts it;
    # the landmarker stub produces 3 landmarks -> 9-value embeddings.
    registry.write_text(json.dumps({"version": 1, "faces": {"Odd": [0.75] * 8}}))

    session = StreamSession(
        width=W, height=H, fps=50.0, source=None,
        analysis=True, known_faces=registry,
    )
    session.analysis_interval = 0.0  # analyse every frame
    session._models_ready.set()
    # Stub the library boundary only: _detect returns real landmark objects,
    # so _embedding / _nearest / the tick arithmetic all run for real.
    session.face_recognizer._model = object()
    session.face_recognizer._detect = lambda frame: SimpleNamespace(
        face_landmarks=[[SimpleNamespace(x=0.5, y=0.5, z=0.0)] * 3]
    )
    check("registry loaded the odd-width entry",
          session.face_store.faces.get("Odd") is not None
          and session.face_store.faces["Odd"].shape == (8,),
          f"faces={ {k: v.shape for k, v in session.face_store.faces.items()} }")

    stop = asyncio.Event()
    pump = asyncio.create_task(session.run_forever(stop))
    try:
        deadline = time.monotonic() + 8.0
        value = 0
        while session._frames < 3 and not pump.done() and time.monotonic() < deadline:
            value += 1
            session.inject_frame(np.full((H, W, 3), value, dtype=np.uint8))
            await asyncio.sleep(0.02)

        if pump.done():
            exc = pump.exception()
            if expect_dead:
                check("guard removed -> ValueError kills the pump",
                      isinstance(exc, ValueError) and "broadcast" in str(exc),
                      f"exception={exc!r}")
            else:
                check("PUMP ALIVE with a wrong-width registry", False,
                      f"pump died: {exc!r}")
        else:
            check("PUMP ALIVE with a wrong-width registry",
                  not expect_dead,
                  "pump survived" if not expect_dead
                  else "expected the pump to die under the mutant")
            check("frames kept being encoded", session._frames >= 3,
                  f"frames={session._frames}")
            status = session.status()
            check("status() still answers", isinstance(status, dict)
                  and status.get("frames", 0) >= 3,
                  f"status.frames={status.get('frames')}")
            # The odd entry must not match anything (it cannot be compared).
            # STATE_RUNNING's literal is "mediapipe" (rvm.analysis.states).
            face_result = status["face_identities"]
            check("analysis tick still ran (a face was seen)",
                  face_result.get("state") == "mediapipe"
                  and face_result.get("seen", 0) >= 1,
                  f"face_identities={face_result}")
            check("wrong-width entry never produces an identity",
                  face_result.get("identities") == [],
                  f"identities={face_result.get('identities')}")
    finally:
        stop.set()
        if pump.done():
            try:
                pump.exception()
            except asyncio.CancelledError:
                pass
        else:
            await asyncio.wait_for(pump, timeout=5.0)
        session.close()

    fails = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
    return 1 if fails else 0


results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
