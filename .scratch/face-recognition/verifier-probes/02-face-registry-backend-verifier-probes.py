"""Verifier probes for ticket 02 — face registry backend (round 1).

Independent probes: everything here calls the code or the live HTTP surface
itself; nothing is transcribed from the implementer's tests or selfcheck.

Usage (from the verification worktree or anywhere):

    python 02-face-registry-backend-verifier-probes.py <subcommand> [args]

Subcommands:
    sample      direct FaceRecognizer.sample_faces calls (empty/multi/dims)
    api         in-process real-HTTP probes with stubbed landmarker inference
    live        real-process probes against run_server.py --no-camera
    persist     real-process persistence + --known-faces + corrupt-file probes
    churn       in-process dict-replacement race (no 'dictionary changed size')
    stress      live-process status/MJPEG latency during a registration burst
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

import numpy as np

# OpenCV 4.14 aborts in clReleaseDevice at process exit after Haar
# detection ran on a worker thread; the OpenCL path is irrelevant to
# these probes (same workaround the test suite uses).
try:
    import cv2
    cv2.ocl.setUseOpenCL(False)
except Exception:  # noqa: BLE001
    pass

WORKTREE = Path(os.environ.get(
    "VERIFY_WT",
    r"C:\Users\joe\AppData\Local\Temp\verify-02-r1-5adcede",
))
sys.path.insert(0, str(WORKTREE / "src"))

PY = os.environ.get(
    "VERIFY_PY",
    r"C:\Users\joe\Desktop\工作学习\study 2026-2027 sem1\EIE4428-Multimedia-Communications"
    r"\mini-project\EIE4428-RVM\EIE4428-RVM\.venv\Scripts\python.exe",
)

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}", flush=True)


def summary() -> int:
    fails = [r for r in results if r[0] == FAIL]
    print(f"\n== {len(results) - len(fails)}/{len(results)} checks passed ==")
    return 1 if fails else 0


# ---------------------------------------------------------------- sample ---
def cmd_sample() -> int:
    """Direct sample_faces calls: empty frame, multi-face, dimension rules."""
    from rvm.analysis.recognition import FaceRecognizer, FaceSamplingError

    # 1) Real landmarker on a blank frame -> empty list (real inference path).
    rec = FaceRecognizer()
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    got = rec.sample_faces(blank)
    check("sample_faces blank frame -> []", got == [], f"got {got!r}")

    # also a noisy synthetic frame (still no face) -> []
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (240, 320, 3), dtype=np.uint8)
    got = rec.sample_faces(noise)
    check("sample_faces noise frame -> []", got == [], f"got {got!r}")

    # 2) Multi-face: stub _detect to return two landmark sets (478 each, like
    # the real model) and verify one embedding per face + consistent dims.
    class _LM:
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z

    class _Result:
        def __init__(self, faces):
            self.face_landmarks = faces

    rec2 = FaceRecognizer()
    face_a = [_LM(0.1 * i / 478, 0.2, 0.01) for i in range(478)]
    face_b = [_LM(0.9 - 0.1 * i / 478, 0.8, -0.01) for i in range(478)]
    rec2._detect = lambda frame: _Result([face_a, face_b])  # noqa: SLF001
    rec2._model = object()  # pretend loaded so _load_model() returns truthy
    got = rec2.sample_faces(blank)
    check(
        "sample_faces 2-face frame -> 2 embeddings",
        isinstance(got, list) and len(got) == 2,
        f"len={len(got)}",
    )
    dims = {e.shape for e in got}
    check(
        "embeddings are 1-D and equal-dimensioned",
        len(dims) == 1 and got[0].ndim == 1,
        f"dims={dims}",
    )
    check(
        "embedding dim == 3 x landmark count (478->1434)",
        got[0].shape[0] == 3 * 478,
        f"dim={got[0].shape[0]}",
    )
    check(
        "the two embeddings differ (per-face, not broadcast)",
        not np.array_equal(got[0], got[1]),
        "",
    )

    # 3) No model -> FaceSamplingError (not an empty list).
    rec3 = FaceRecognizer()
    rec3._failure = "probe: no model"  # noqa: SLF001
    rec3._model = None  # noqa: SLF001
    try:
        rec3.sample_faces(blank)
        check("missing model raises FaceSamplingError", False, "returned instead")
    except FaceSamplingError as exc:
        check("missing model raises FaceSamplingError", True, f"{exc}")
    except Exception as exc:  # noqa: BLE001
        check(
            "missing model raises FaceSamplingError",
            False,
            f"raised {type(exc).__name__}",
        )
    return summary()


# ------------------------------------------------------------------- api ---
def cmd_api() -> int:
    """Real HTTP surface (aiohttp server) with stubbed landmarker inference.

    Everything is real — TCP, handlers, to_thread, session, lock, FaceStore —
    except the MediaPipe landmarker, which no synthetic frame can satisfy.
    """
    import aiohttp
    from aiohttp import web

    from rvm.analysis.face_store import FaceStore
    from rvm.server.app import SESSION, create_app
    from rvm.server.session import StreamSession

    async def main() -> int:
        tmp = Path(tempfile.mkdtemp(prefix="v02api-"))
        store_path = tmp / "sub" / "faces.json"
        session = StreamSession(
            width=320,
            height=240,
            fps=5.0,
            source=None,
            analysis=True,
            known_faces=store_path,
        )
        # Pretend warm-up finished; feed three analysed frames.
        session._models_ready.set()  # noqa: SLF001
        session._recent_frames = [  # noqa: SLF001
            np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(4)
        ]

        # Stub inference: per-call crafted embeddings; verifies 3 frames used.
        call_vectors = [
            np.full(1434, 10.0),
            np.full(1434, 20.0),
            np.full(1434, 30.0),
        ]
        state = {"mode": "one", "i": 0}

        def fake_sample(frame):
            if state["mode"] == "none":
                return []
            if state["mode"] == "two":
                return [np.full(1434, 1.0), np.full(1434, 2.0)]
            vec = call_vectors[min(state["i"], len(call_vectors) - 1)]
            state["i"] += 1
            return [vec]

        session.face_recognizer.sample_faces = fake_sample

        app = create_app(session=session)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
        base = f"http://127.0.0.1:{port}"
        print(f"in-process server on {base}; store={store_path}", flush=True)

        def file_state():
            if not store_path.exists():
                return None
            return hashlib.sha256(store_path.read_bytes()).hexdigest()

        try:
            async with aiohttp.ClientSession() as http:
                # -- happy path: POST -> 201, 3 samples, mean vector on disk --
                async with http.post(
                    f"{base}/api/faces/known", json={"name": "Alice Ng"}
                ) as r:
                    body = await r.json()
                    check(
                        "POST one-face frames -> 201",
                        r.status == 201,
                        f"status={r.status} body={body}",
                    )
                    check(
                        "201 body contract {name,samples,known}",
                        body.get("name") == "Alice Ng"
                        and body.get("samples") == 3
                        and body.get("known") == ["Alice Ng"],
                        f"body={body}",
                    )
                check(
                    "registry file was written",
                    store_path.exists(),
                    f"{store_path}",
                )
                stored = FaceStore(store_path).load()
                vec = stored.get("Alice Ng")
                check(
                    "stored vector == mean of the 3 frame embeddings (20.0)",
                    vec is not None
                    and np.allclose(vec, np.full(1434, 20.0)),
                    f"mean={None if vec is None else vec[:3]}",
                )
                check(
                    "exactly 3 sampling calls for 4 recent frames (last 3)",
                    state["i"] == 3,
                    f"calls={state['i']}",
                )

                # -- 409 name-exists, file untouched --
                before = file_state()
                async with http.post(
                    f"{base}/api/faces/known", json={"name": "Alice Ng"}
                ) as r:
                    body = await r.json()
                    check(
                        "duplicate name -> 409 name-exists",
                        r.status == 409 and body.get("reason") == "name-exists",
                        f"status={r.status} body={body}",
                    )
                check("name-exists left file byte-identical", file_state() == before)

                # -- 409 no-face, file untouched --
                state["mode"] = "none"
                before = file_state()
                async with http.post(
                    f"{base}/api/faces/known", json={"name": "Bob"}
                ) as r:
                    body = await r.json()
                    check(
                        "no faces -> 409 no-face",
                        r.status == 409 and body.get("reason") == "no-face",
                        f"status={r.status} body={body}",
                    )
                check("no-face left file byte-identical", file_state() == before)

                # -- 409 multiple-faces, file untouched --
                state["mode"] = "two"
                before = file_state()
                async with http.post(
                    f"{base}/api/faces/known", json={"name": "Bob"}
                ) as r:
                    body = await r.json()
                    check(
                        "two faces -> 409 multiple-faces",
                        r.status == 409
                        and body.get("reason") == "multiple-faces",
                        f"status={r.status} body={body}",
                    )
                check("multiple-faces left file byte-identical", file_state() == before)
                state["mode"] = "one"

                # -- 400 bad-name variants, file untouched --
                bad_payloads = [
                    {"name": ""},
                    {"name": "   "},
                    {"name": 123},
                    {"name": "x" * 41},
                    {"name": "two\nlines"},
                    {"name": "tab\tchar"},
                    {},
                    {"other": "Alice"},
                ]
                for payload in bad_payloads:
                    before = file_state()
                    async with http.post(
                        f"{base}/api/faces/known", json=payload
                    ) as r:
                        body = await r.json()
                        check(
                            f"bad-name {payload!r} -> 400",
                            r.status == 400 and body.get("reason") == "bad-name",
                            f"status={r.status} body={body}",
                        )
                    if file_state() != before:
                        check(f"file untouched after {payload!r}", False)
                # non-JSON body
                before = file_state()
                async with http.post(
                    f"{base}/api/faces/known",
                    data=b"not json{",
                    headers={"Content-Type": "application/json"},
                ) as r:
                    body = await r.json()
                    check(
                        "malformed JSON -> 400 bad-name",
                        r.status == 400 and body.get("reason") == "bad-name",
                        f"status={r.status} body={body}",
                    )
                check("malformed JSON left file identical", file_state() == before)
                # non-dict JSON
                async with http.post(f"{base}/api/faces/known", json=[1, 2]) as r:
                    body = await r.json()
                    check(
                        "JSON array body -> 400 bad-name",
                        r.status == 400 and body.get("reason") == "bad-name",
                        f"status={r.status} body={body}",
                    )

                # -- GET contract & order --
                session.face_store.add("Bob", np.full(1434, 5.0))
                session.face_store.save()
                session.face_recognizer.replace_known_faces(session.face_store.faces)
                async with http.get(f"{base}/api/faces/known") as r:
                    body = await r.json()
                    check(
                        "GET returns sorted names",
                        r.status == 200 and body == {"known": ["Alice Ng", "Bob"]},
                        f"status={r.status} body={body}",
                    )

                # -- DELETE existing -> file written immediately --
                before = file_state()
                async with http.delete(f"{base}/api/faces/known/Alice%20Ng") as r:
                    body = await r.json()
                    check(
                        "DELETE -> 200 {removed,known}",
                        r.status == 200
                        and body.get("removed") is True
                        and body.get("known") == ["Bob"],
                        f"status={r.status} body={body}",
                    )
                check("DELETE rewrote the file", file_state() not in (before, None))
                stored = FaceStore(store_path).load()
                check(
                    "deleted name is gone from disk",
                    "Alice Ng" not in stored and "Bob" in stored,
                    f"on disk={sorted(stored)}",
                )

                # -- DELETE missing -> 404 --
                before = file_state()
                async with http.delete(f"{base}/api/faces/known/Nobody") as r:
                    body = await r.json()
                    check(
                        "DELETE unknown -> 404 contract body",
                        r.status == 404 and "reason" in body and "error" in body,
                        f"status={r.status} body={body}",
                    )
                check("404 left file byte-identical", file_state() == before)

                # -- 503 analysis-disabled --
                session2 = StreamSession(
                    width=320, height=240, fps=5.0, source=None,
                    analysis=False, known_faces=tmp / "s2.json",
                )
                session2._recent_frames = [blank := np.zeros((240, 320, 3), np.uint8)] * 3  # noqa: SLF001
                app2 = create_app(session=session2)
                r2 = web.AppRunner(app2)
                await r2.setup()
                s2 = web.TCPSite(r2, "127.0.0.1", 0)
                await s2.start()
                port2 = s2._server.sockets[0].getsockname()[1]  # noqa: SLF001
                async with http.post(
                    f"http://127.0.0.1:{port2}/api/faces/known",
                    json={"name": "Carol"},
                ) as r:
                    body = await r.json()
                    check(
                        "analysis off -> 503 analysis-disabled",
                        r.status == 503
                        and body.get("reason") == "analysis-disabled",
                        f"status={r.status} body={body}",
                    )
                check("analysis-disabled wrote no file", not (tmp / "s2.json").exists())
                await r2.cleanup()

                # -- 503 models-loading --
                session3 = StreamSession(
                    width=320, height=240, fps=5.0, source=None,
                    analysis=True, known_faces=tmp / "s3.json",
                )
                # _models_ready NOT set -> still loading.
                session3._warmup = None  # noqa: SLF001
                app3 = create_app(session=session3)
                r3 = web.AppRunner(app3)
                await r3.setup()
                s3 = web.TCPSite(r3, "127.0.0.1", 0)
                await s3.start()
                port3 = s3._server.sockets[0].getsockname()[1]  # noqa: SLF001
                async with http.post(
                    f"http://127.0.0.1:{port3}/api/faces/known",
                    json={"name": "Dave"},
                ) as r:
                    body = await r.json()
                    check(
                        "models loading -> 503 models-loading",
                        r.status == 503
                        and body.get("reason") == "models-loading",
                        f"status={r.status} body={body}",
                    )
                check("models-loading wrote no file", not (tmp / "s3.json").exists())
                await r3.cleanup()

                # -- 503 unavailable (sampling raises FaceSamplingError) --
                from rvm.analysis.recognition import FaceSamplingError

                def boom(frame):
                    raise FaceSamplingError("probe: landmarker dead")

                session.face_recognizer.sample_faces = boom
                before = file_state()
                async with http.post(
                    f"{base}/api/faces/known", json={"name": "Eve"}
                ) as r:
                    body = await r.json()
                    check(
                        "sampling failure -> 503 unavailable",
                        r.status == 503 and body.get("reason") == "unavailable",
                        f"status={r.status} body={body}",
                    )
                check("unavailable left file identical", file_state() == before)
        finally:
            await runner.cleanup()
        return summary()

    return asyncio.run(main())


# ------------------------------------------------------------------ live ---
def _http(method: str, url: str, body=None, timeout: float = 10.0):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:  # noqa: BLE001
            return e.code, {}


def _wait_http(base: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/status", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.05)
    return False


def _start_server(args: list[str], cwd: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [PY, str(WORKTREE / "run_server.py"), *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop(proc: subprocess.Popen) -> str:
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=10)
    return out or ""


def cmd_live() -> int:
    """Real-process probes: every inference runs the real MediaPipe stack."""
    tmp = Path(tempfile.mkdtemp(prefix="v02live-"))
    store = tmp / "data" / "known_faces.json"
    proc = _start_server(
        ["--no-camera", "--port", "18231", "--fps", "10",
         "--known-faces", str(store)],
        cwd=tmp,
    )
    try:
        check("server process started", proc.poll() is None)

        # -- 503 models-loading: hit POST while warm-up is still running --
        loading_seen = None
        deadline = time.time() + 20
        while time.time() < deadline and loading_seen is None:
            try:
                status, body = _http(
                    "POST", "http://127.0.0.1:18231/api/faces/known",
                    {"name": "Early"}, timeout=2,
                )
                if status == 503:
                    loading_seen = body.get("reason")
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        check(
            "POST during warm-up -> 503 models-loading",
            loading_seen == "models-loading",
            f"reason={loading_seen!r} (none = warm-up won the race)",
        )
        check("models-loading wrote no file", not store.exists())

        # wait until analyses are actually running (>=3 recent frames)
        if not _wait_http("http://127.0.0.1:18231"):
            check("server reachable", False)
            return summary()
        time.sleep(3.0)  # model load ~2-3 s + a few analysis ticks

        # -- 409 no-face on the synthetic scene (real landmarker, real lock) --
        status, body = _http(
            "POST", "http://127.0.0.1:18231/api/faces/known", {"name": "Zed"}
        )
        check(
            "synthetic scene -> 409 no-face",
            status == 409 and body.get("reason") == "no-face",
            f"status={status} body={body}",
        )
        check("no-face wrote no file", not store.exists())

        # -- 409 name-exists: seed the file, restart-free reload? --
        # name-exists is checked before sampling, so a seeded list suffices.
        out = _stop(proc)
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps({
            "version": 1,
            "faces": {"Seeded": [0.5] * 1434},
        }))
        proc = _start_server(
            ["--no-camera", "--port", "18231", "--fps", "10",
             "--known-faces", str(store)],
            cwd=tmp,
        )
        _wait_http("http://127.0.0.1:18231")
        before = hashlib.sha256(store.read_bytes()).hexdigest()
        status, body = _http(
            "GET", "http://127.0.0.1:18231/api/faces/known"
        )
        check(
            "seeded list served after start",
            status == 200 and body == {"known": ["Seeded"]},
            f"status={status} body={body}",
        )
        status, body = _http(
            "POST", "http://127.0.0.1:18231/api/faces/known",
            {"name": "Seeded"},
        )
        check(
            "duplicate of seeded name -> 409 name-exists",
            status == 409 and body.get("reason") == "name-exists",
            f"status={status} body={body}",
        )
        check(
            "name-exists left file byte-identical",
            hashlib.sha256(store.read_bytes()).hexdigest() == before,
        )

        # -- DELETE over real HTTP writes the file --
        status, body = _http(
            "DELETE", "http://127.0.0.1:18231/api/faces/known/Seeded"
        )
        check(
            "DELETE -> 200 removed",
            status == 200 and body.get("removed") is True
            and body.get("known") == [],
            f"status={status} body={body}",
        )
        disk = json.loads(store.read_text())
        check(
            "delete is on disk immediately",
            disk.get("faces") == {},
            f"faces={disk.get('faces')}",
        )
        status, body = _http(
            "DELETE", "http://127.0.0.1:18231/api/faces/known/Seeded"
        )
        check(
            "DELETE again -> 404",
            status == 404 and "reason" in body and "error" in body,
            f"status={status} body={body}",
        )
        _stop(proc)

        # -- 503 analysis-disabled: real process with --no-analysis --
        proc = _start_server(
            ["--no-camera", "--no-analysis", "--port", "18231",
             "--known-faces", str(store)],
            cwd=tmp,
        )
        _wait_http("http://127.0.0.1:18231")
        status, body = _http(
            "POST", "http://127.0.0.1:18231/api/faces/known", {"name": "Ana"}
        )
        check(
            "--no-analysis -> 503 analysis-disabled",
            status == 503 and body.get("reason") == "analysis-disabled",
            f"status={status} body={body}",
        )
        _stop(proc)

        # -- 503 unavailable: remove the face landmarker model in the copy --
        model = WORKTREE / "models" / "face_landmarker.task"
        hidden = model.with_suffix(".task.hidden")
        if model.exists():
            model.rename(hidden)
        try:
            proc = _start_server(
                ["--no-camera", "--port", "18231", "--fps", "10",
                 "--known-faces", str(store)],
                cwd=tmp,
            )
            _wait_http("http://127.0.0.1:18231")
            time.sleep(3.0)  # warm-up fails fast; need >=3 analysed frames
            time.sleep(1.5)
            status, body = _http(
                "POST", "http://127.0.0.1:18231/api/faces/known",
                {"name": "Ghost"},
            )
            check(
                "missing landmarker model -> 503 unavailable",
                status == 503 and body.get("reason") == "unavailable",
                f"status={status} body={body}",
            )
            _stop(proc)
        finally:
            if hidden.exists():
                hidden.rename(model)
    finally:
        if proc.poll() is None:
            _stop(proc)
    return summary()


# --------------------------------------------------------------- persist ---
def cmd_persist() -> int:
    """Restart persistence, --known-faces path, default path, corrupt file."""
    tmp = Path(tempfile.mkdtemp(prefix="v02persist-"))
    custom = tmp / "elsewhere" / "my_faces.json"

    # seed via a real process using --known-faces
    custom.parent.mkdir(parents=True)
    custom.write_text(json.dumps({
        "version": 1, "faces": {"Alice Ng": [0.25] * 1434, "Bob": [0.75] * 8},
    }))
    proc = _start_server(
        ["--no-camera", "--port", "18232", "--known-faces", str(custom)],
        cwd=tmp,
    )
    try:
        _wait_http("http://127.0.0.1:18232")
        status, body = _http("GET", "http://127.0.0.1:18232/api/faces/known")
        check(
            "--known-faces path is honoured on load",
            status == 200 and body == {"known": ["Alice Ng", "Bob"]},
            f"status={status} body={body}",
        )
    finally:
        _stop(proc)

    # restart -> still there (persistence across processes)
    proc = _start_server(
        ["--no-camera", "--port", "18232", "--known-faces", str(custom)],
        cwd=tmp,
    )
    try:
        _wait_http("http://127.0.0.1:18232")
        status, body = _http("GET", "http://127.0.0.1:18232/api/faces/known")
        check(
            "restart keeps the list",
            status == 200 and body == {"known": ["Alice Ng", "Bob"]},
            f"status={status} body={body}",
        )
        # delete -> file sync
        _http("DELETE", "http://127.0.0.1:18232/api/faces/known/Bob")
        disk = json.loads(custom.read_text())
        check(
            "delete synced to disk",
            sorted(disk.get("faces", {})) == ["Alice Ng"],
            f"faces={sorted(disk.get('faces', {}))}",
        )
    finally:
        _stop(proc)

    # default path: cwd-relative data/known_faces.json
    default_cwd = tmp / "dfltcwd"
    default_cwd.mkdir()
    (default_cwd / "data").mkdir()
    (default_cwd / "data" / "known_faces.json").write_text(json.dumps({
        "version": 1, "faces": {"DefaultPath": [0.1] * 10},
    }))
    proc = _start_server(["--no-camera", "--port", "18232"], cwd=default_cwd)
    try:
        _wait_http("http://127.0.0.1:18232")
        status, body = _http("GET", "http://127.0.0.1:18232/api/faces/known")
        check(
            "default path = <cwd>/data/known_faces.json",
            status == 200 and body == {"known": ["DefaultPath"]},
            f"status={status} body={body}",
        )
    finally:
        _stop(proc)

    # corrupt file -> warning + empty list, server still serves
    broken = tmp / "broken" / "faces.json"
    broken.parent.mkdir(exist_ok=True)
    broken.write_text("{ definitely not json ]")
    proc = _start_server(
        ["--no-camera", "--port", "18232", "--known-faces", str(broken)],
        cwd=tmp,
    )
    try:
        _wait_http("http://127.0.0.1:18232")
        status, body = _http("GET", "http://127.0.0.1:18232/api/faces/known")
        check(
            "corrupt registry degrades to empty list",
            status == 200 and body == {"known": []},
            f"status={status} body={body}",
        )
        status, _ = _http("GET", "http://127.0.0.1:18232/api/status")
        check("corrupt registry did not crash the server", status == 200)
        out = _stop(proc)
        check(
            "corrupt file produced a warning in the log",
            "corrupt" in out.lower() or "warning" in out.lower(),
            f"log tail={out[-200:]!r}",
        )
        proc = None
    finally:
        if proc is not None and proc.poll() is None:
            _stop(proc)

    # wrong-shape file also degrades
    broken.write_text(json.dumps({"version": 1, "faces": {"X": "notalist"}}))
    proc = _start_server(
        ["--no-camera", "--port", "18232", "--known-faces", str(broken)],
        cwd=tmp,
    )
    try:
        _wait_http("http://127.0.0.1:18232")
        status, body = _http("GET", "http://127.0.0.1:18232/api/faces/known")
        check(
            "wrong-shape registry degrades to empty list",
            status == 200 and body == {"known": []},
            f"status={status} body={body}",
        )
    finally:
        _stop(proc)
    return summary()


# ----------------------------------------------------------------- churn ---
def cmd_churn() -> int:
    """dict-replacement race: iterate known_faces while it is re-published."""
    from rvm.analysis.recognition import FaceRecognizer
    from rvm.analysis.face_store import FaceStore
    from rvm.server.session import StreamSession

    # direct recognizer churn: reader iterates, writer replaces
    rec = FaceRecognizer()
    rec.known_faces = {f"p{i}": np.full(1434, i / 100.0) for i in range(2000)}
    errors: list[str] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            known = rec.known_faces
            try:
                for name, vec in known.items():  # iteration across replacement
                    _ = (name, vec[:1])
            except RuntimeError as exc:
                errors.append(str(exc))
                return

    def writer():
        for i in range(3000):
            if i % 2:
                rec.add_known_face(f"n{i}", np.zeros(1434))
            else:
                rec.remove_known_face(f"n{i - 1}")

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    writer()
    stop.set()
    for t in threads:
        t.join()
    check(
        "3000 add/remove vs 4 iterating readers: no dict-changed-size",
        not errors,
        f"errors={errors[:2]}",
    )

    # session-level churn: repeated register/remove while a reader iterates
    tmp = Path(tempfile.mkdtemp(prefix="v02churn-"))
    session = StreamSession(
        width=320, height=240, fps=5.0, source=None,
        analysis=True, known_faces=tmp / "faces.json",
    )
    session._models_ready.set()  # noqa: SLF001
    session._recent_frames = [np.zeros((240, 320, 3), np.uint8)] * 3  # noqa: SLF001
    session.face_recognizer.sample_faces = lambda f: [np.full(1434, 1.0)]
    errors2: list[str] = []
    stop2 = threading.Event()

    def reader2():
        while not stop2.is_set():
            try:
                for n, v in session.face_recognizer.known_faces.items():
                    _ = (n, v[:1])
            except RuntimeError as exc:
                errors2.append(str(exc))
                return

    stop2.clear()
    threads = [threading.Thread(target=reader2) for _ in range(4)]
    for t in threads:
        t.start()
    done = 0
    for i in range(120):
        try:
            session.register_face(f"user{i}")
            done += 1
            session.remove_face(f"user{i}")
        except Exception as exc:  # noqa: BLE001
            errors2.append(f"register/remove: {exc}")
            break
    stop2.set()
    for t in threads:
        t.join()
    check(
        "120 register+remove cycles vs iterating readers: clean",
        not errors2 and done == 120,
        f"done={done} errors={errors2[:2]}",
    )
    check(
        "final registry empty on disk",
        json.loads((tmp / "faces.json").read_text()).get("faces") == {},
    )
    return summary()


# ---------------------------------------------------------------- stress ---
def cmd_stress() -> int:
    """Live server: /api/status latency + MJPEG frames during a POST burst."""
    tmp = Path(tempfile.mkdtemp(prefix="v02stress-"))
    store = tmp / "faces.json"
    proc = _start_server(
        ["--no-camera", "--port", "18233", "--fps", "15",
         "--known-faces", str(store)],
        cwd=tmp,
    )
    try:
        _wait_http("http://127.0.0.1:18233")
        time.sleep(4.0)  # models loaded + analysis running

        def status_latencies(n: int) -> list[float]:
            lat = []
            for _ in range(n):
                t0 = time.perf_counter()
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:18233/api/status", timeout=5
                    ) as r:
                        r.read()
                    lat.append((time.perf_counter() - t0) * 1000)
                except Exception as exc:  # noqa: BLE001
                    lat.append(float("inf"))
            return lat

        def mjpeg_frames(seconds: float) -> int:
            """Count multipart JPEG frames in a window."""
            frames = 0
            req = urllib.request.Request(
                "http://127.0.0.1:18233/api/stream.mjpg"
            )
            deadline = time.time() + seconds
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    buf = b""
                    while time.time() < deadline:
                        chunk = r.read(8192)
                        if not chunk:
                            break
                        buf += chunk
                        frames += buf.count(b"\r\n\r\n\xff\xd8")
                        buf = buf[-16:]
            except Exception as exc:  # noqa: BLE001
                print(f"mjpeg read ended early: {exc}")
            return frames

        # baseline
        base_lat = status_latencies(20)
        base_frames = mjpeg_frames(3.0)

        # registration burst: each POST runs 3 real landmarker inferences
        # under the shared lock before returning 409 no-face.
        burst_errors: list[str] = []
        def burst():
            for i in range(24):
                try:
                    status, _ = _http(
                        "POST",
                        "http://127.0.0.1:18233/api/faces/known",
                        {"name": f"burst{i}"}, timeout=15,
                    )
                    if status not in (201, 400, 404, 409, 500, 503):
                        burst_errors.append(f"status {status}")
                except Exception as exc:  # noqa: BLE001
                    burst_errors.append(str(exc))

        mj_result: list[int] = []
        def mjpeg_worker():
            mj_result.append(mjpeg_frames(6.0))

        bt = threading.Thread(target=burst)
        mt = threading.Thread(target=mjpeg_worker)
        mt.start()
        bt.start()
        load_lat = status_latencies(20)
        bt.join()
        mt.join()

        def pct(values, p):
            finite = sorted(v for v in values if v != float("inf"))
            if not finite:
                return float("inf")
            return finite[min(len(finite) - 1, int(len(finite) * p))]

        b50, b95 = pct(base_lat, 0.5), pct(base_lat, 0.95)
        l50, l95 = pct(load_lat, 0.5), pct(load_lat, 0.95)
        print(
            f"status latency ms: baseline p50={b50:.1f} p95={b95:.1f} | "
            f"burst p50={l50:.1f} p95={l95:.1f}"
        )
        print(
            f"mjpeg frames: baseline {base_frames}/3s | burst {mj_result[0]}/6s "
            f"({mj_result[0] / 2:.1f} vs {base_frames / 3:.1f} fps equiv)"
        )
        check(
            "no burst request errored or hung",
            not burst_errors,
            f"errors={burst_errors[:3]}",
        )
        check(
            "status p95 during burst < 500 ms (event loop not stalled)",
            l95 < 500.0,
            f"p95={l95:.1f}ms",
        )
        check(
            "MJPEG kept delivering frames during burst (>=2 fps equiv)",
            mj_result[0] >= 12,
            f"frames={mj_result[0]} in 6s",
        )
    finally:
        _stop(proc)
    return summary()


COMMANDS = {
    "sample": cmd_sample,
    "api": cmd_api,
    "live": cmd_live,
    "persist": cmd_persist,
    "churn": cmd_churn,
    "stress": cmd_stress,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]]())
