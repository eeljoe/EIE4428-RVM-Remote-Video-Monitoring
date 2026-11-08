#!/usr/bin/env python3
"""Independent r2 verifier probe: registry concurrency.

Part A -- the r2 remediation, re-derived without the adopted test: two threads
call ``StreamSession.register_face`` for the same name through a slowed
landmarker; exactly one may succeed and the file must hold exactly one entry.

Part B -- adversarial follow-up the remediation did not cover: ``remove_face``
copies ``face_store.faces`` and checks membership OUTSIDE ``_faces_lock``
(session.py:687-693), so a register that commits between that copy and the
remove's ``_publish_faces`` is silently dropped.  The probe demonstrates the
interleaving by holding ``_faces_lock`` so a racing register is queued ahead
of the remove's publish -- the same thing an OS preemption between the copy
and the publish produces in production.

    python 02-r2-verifier-race.py

Env: VERIFY_WT (verification worktree, required).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

WORKTREE = Path(os.environ["VERIFY_WT"])
sys.path.insert(0, str(WORKTREE / "src"))

try:
    import cv2
    cv2.ocl.setUseOpenCL(False)
except Exception:  # noqa: BLE001
    pass

from rvm.server.session import FaceRequestError, StreamSession  # noqa: E402

W, H = 320, 240
PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" -- {detail}" if detail else ""))


def make_session(tmp: Path, slow: float = 0.0) -> StreamSession:
    session = StreamSession(
        width=W, height=H, fps=50.0, source=None,
        analysis=True, known_faces=tmp / "known_faces.json",
    )
    session._models_ready.set()
    session._recent_frames = [
        np.zeros((H, W, 3), dtype=np.uint8) for _ in range(3)
    ]

    def sample(frame):
        if slow:
            time.sleep(slow)
        return [np.full(8, float(frame[0, 0, 0]) + 1.0)]

    session.face_recognizer.sample_faces = sample
    return session


def register_outcome(session: StreamSession, name: str) -> tuple[int, str | None]:
    try:
        session.register_face(name)
        return 201, None
    except FaceRequestError as exc:
        return exc.status, exc.reason


def part_a(tmp: Path) -> None:
    print("--- Part A: two threads, one name ---")
    session = make_session(tmp / "a", slow=0.05)
    session._recent_frames = [
        np.full((H, W, 3), v, dtype=np.uint8) for v in (10, 20, 30)
    ]
    try:
        outcomes: list[tuple[int, str | None]] = []
        threads = [
            threading.Thread(
                target=lambda: outcomes.append(register_outcome(session, "Alice"))
            )
            for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        codes = sorted(code for code, _ in outcomes)
        reasons = sorted(reason for _, reason in outcomes if reason)
        check("two concurrent same-name registrations -> exactly one 201",
              codes == [201, 409], f"outcomes={outcomes}")
        check("the refused one says name-exists", reasons == ["name-exists"],
              f"reasons={reasons}")
        stored = json.loads(
            (tmp / "a" / "known_faces.json").read_text(encoding="utf-8")
        )
        check("the file holds exactly one entry",
              list(stored.get("faces", {})) == ["Alice"],
              f"faces={list(stored.get('faces', {}))}")
        check("store and recogniser mirror agree",
              set(session.face_store.faces)
              == set(session.face_recognizer.known_faces),
              f"store={sorted(session.face_store.faces)} "
              f"mirror={sorted(session.face_recognizer.known_faces)}")
    finally:
        session.close()


def part_b(tmp: Path) -> None:
    print("--- Part B: register vs remove, stale copy ---")
    losses = 0
    rounds = 0
    for attempt in range(10):
        session = make_session(tmp / f"b{attempt}")
        # Seed {Ada, Bob} directly: the race under study is between the two
        # mutations, not the sampling that produced them.
        seed = {"Ada": np.full(8, 1.0), "Bob": np.full(8, 2.0)}
        session.face_store.replace(seed)
        session.face_recognizer.replace_known_faces(seed)
        session.face_store.save()
        try:
            # Hold the registry lock so the two racing mutations queue in a
            # known order: register first, remove second.  The remove's stale
            # copy is taken before either of them proceeds -- identical to the
            # interleaving a preemption between session.py:687 and :693 gives.
            session._faces_lock.acquire()
            done: dict[str, tuple[int, str | None]] = {}

            def register():
                done["register"] = register_outcome(session, "Carol")

            def remove():
                try:
                    session.remove_face("Ada")
                    done["remove"] = (200, None)
                except FaceRequestError as exc:
                    done["remove"] = (exc.status, exc.reason)

            t_reg = threading.Thread(target=register)
            t_reg.start()
            time.sleep(0.15)  # let register finish sampling and queue on the lock
            t_rem = threading.Thread(target=remove)
            t_rem.start()
            time.sleep(0.15)  # let remove take its stale copy and queue behind
            session._faces_lock.release()
            t_reg.join(timeout=10)
            t_rem.join(timeout=10)
            assert not t_reg.is_alive() and not t_rem.is_alive(), "deadlock"

            rounds += 1
            final = set(session.face_store.faces)
            mirror = set(session.face_recognizer.known_faces)
            disk = set(json.loads(
                (tmp / f"b{attempt}" / "known_faces.json").read_text()
            ).get("faces", {}))
            consistent = final == mirror == disk
            check(f"round {attempt}: file/store/mirror still consistent",
                  consistent,
                  f"store={sorted(final)} mirror={sorted(mirror)} disk={sorted(disk)}")
            if done.get("register", (0,))[0] == 201 and "Carol" not in final:
                losses += 1
                print(f"    LOST UPDATE: register said 201, final={sorted(final)}")
        finally:
            session.close()
        if losses:
            break

    check("a 201-confirmed registration can be lost to a racing remove",
          losses >= 1,
          f"{losses} lost-update(s) observed over {rounds} round(s)")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="v02r2race-"))
    part_a(tmp)
    part_b(tmp)
    fails = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
