#!/usr/bin/env python3
"""Independent r2 verifier probe: persistence & degrade on real server processes.

Re-derives the r1 C5/C9 checks under the r2 contract, where a mixed-width
registry is corrupt by design (the r1 gate's own remediation).  Uses real
``run_server.py`` processes; everything it asserts is observed over HTTP and
on disk, nothing from the implementer's tests.

    python 02-r2-verifier-persist.py

Env: VERIFY_WT (verification worktree, required), VERIFY_PY (venv python),
     VERIFY_PORT (first of three consecutive ports, default 18331).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

WORKTREE = Path(os.environ["VERIFY_WT"])
PY = os.environ["VERIFY_PY"]
PORT0 = int(os.environ.get("VERIFY_PORT", "18331"))

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def summary() -> int:
    fails = [r for r in results if r[0] == FAIL]
    print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed")
    return 1 if fails else 0


def _http(method: str, url: str, payload=None, timeout: float = 10.0):
    req = urllib.request.Request(url, method=method)
    if payload is not None:
        req.data = json.dumps(payload).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def _start(args: list[str], cwd: Path) -> subprocess.Popen:
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
        out, _ = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate(timeout=8)
    return out or ""


def _wait(url: str, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url + "/api/status", timeout=2).read()
            return True
        except Exception:  # noqa: BLE001 - server still starting
            time.sleep(0.25)
    return False


def _frames(url: str) -> int:
    status, body = _http("GET", url + "/api/status")
    return int(body.get("frames", -1)) if status == 200 else -1


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="v02r2persist-"))
    port = PORT0
    base = f"http://127.0.0.1:{port}"

    # -- uniform-width seed via --known-faces: loads, survives restart, deletes --
    seed = tmp / "seed" / "faces.json"
    seed.parent.mkdir(parents=True)
    seed.write_text(json.dumps({
        "version": 1,
        "faces": {"Alice Ng": [0.25] * 10, "Bob": [0.75] * 10},
    }))
    proc = _start(["--no-camera", "--port", str(port), "--known-faces", str(seed)], tmp)
    try:
        ok = _wait(base)
        status, body = _http("GET", base + "/api/faces/known")
        check("--known-faces uniform-width list loads",
              ok and status == 200 and body == {"known": ["Alice Ng", "Bob"]},
              f"status={status} body={body}")
    finally:
        _stop(proc)

    proc = _start(["--no-camera", "--port", str(port), "--known-faces", str(seed)], tmp)
    try:
        _wait(base)
        status, body = _http("GET", base + "/api/faces/known")
        check("restart keeps the list",
              status == 200 and body == {"known": ["Alice Ng", "Bob"]},
              f"status={status} body={body}")
        status, body = _http("DELETE", base + "/api/faces/known/Bob")
        check("DELETE returns removed contract",
              status == 200 and body.get("removed") is True
              and body.get("known") == ["Alice Ng"],
              f"status={status} body={body}")
        disk = json.loads(seed.read_text())
        check("delete synced to disk immediately",
              sorted(disk.get("faces", {})) == ["Alice Ng"],
              f"disk faces={sorted(disk.get('faces', {}))}")
    finally:
        _stop(proc)

    # -- mixed-width seed: corrupt under the r2 contract, server survives --
    mixed = tmp / "mixed" / "faces.json"
    mixed.parent.mkdir()
    mixed.write_text(json.dumps({
        "version": 1,
        "faces": {"Alice": [0.5, 0.25], "Bob": [0.5, 0.25, 0.125]},
    }))
    proc = _start(["--no-camera", "--port", str(port), "--known-faces", str(mixed)], tmp)
    try:
        _wait(base)
        status, body = _http("GET", base + "/api/faces/known")
        check("mixed-width registry degrades to empty list",
              status == 200 and body == {"known": []},
              f"status={status} body={body}")
        frames_a = _frames(base)
        time.sleep(2.0)
        frames_b = _frames(base)
        check("picture pump keeps running after degrade",
              frames_a >= 0 and frames_b > frames_a,
              f"frames {frames_a} -> {frames_b}")
        out = _stop(proc)
        check("mixed-width file produced a corrupt warning",
              "corrupt" in out.lower(),
              f"log tail={out[-300:]!r}")
        proc = None
    finally:
        if proc is not None and proc.poll() is None:
            _stop(proc)

    # -- uniform wrong-width seed: loads (guard lives in _nearest, not _parse) --
    odd = tmp / "odd" / "faces.json"
    odd.parent.mkdir()
    odd.write_text(json.dumps({"version": 1, "faces": {"Odd": [0.5] * 8}}))
    proc = _start(["--no-camera", "--port", str(port), "--known-faces", str(odd)], tmp)
    try:
        _wait(base)
        status, body = _http("GET", base + "/api/faces/known")
        check("uniform wrong-width entry still loads (skipped at match time)",
              status == 200 and body == {"known": ["Odd"]},
              f"status={status} body={body}")
        status, _ = _http("GET", base + "/api/status")
        check("server healthy with an odd-width entry loaded", status == 200)
    finally:
        _stop(proc)

    return summary()


if __name__ == "__main__":
    sys.exit(main())
