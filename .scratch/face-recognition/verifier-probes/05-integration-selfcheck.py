#!/usr/bin/env python3
"""05 self-check: the registry across real server processes, driven over HTTP.

The suite's cross-process test runs ``run_server.py --no-analysis`` so it costs
seconds; this probe runs the server the way the demonstration does (analysis on,
models warmed up) and records what a real installation answers.

    .venv\\Scripts\\python.exe .scratch/face-recognition/verifier-probes/05-integration-selfcheck.py

Everything here is observed over HTTP or on disk.  Nothing imports the product.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / ".venv" / "Scripts" / "python.exe"

results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append(("PASS" if ok else "FAIL", name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def http(method: str, url: str, payload=None, timeout: float = 10.0):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def start(known_faces: Path, tmp: Path, *extra: str):
    port = free_port()
    process = subprocess.Popen(
        [str(PY), str(REPO / "run_server.py"), "--no-camera", "--port", str(port),
         "--known-faces", str(known_faces), "--recordings", str(tmp / "clips"), *extra],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit("server exited: " + process.stdout.read()[-800:])
        try:
            urllib.request.urlopen(base + "/api/status", timeout=2.0).read()
            return process, base
        except Exception:  # noqa: BLE001 - still starting
            time.sleep(0.1)
    raise SystemExit(f"server never answered on {base}")


def stop(process: subprocess.Popen) -> str:
    if process.poll() is None:
        process.terminate()
    try:
        output, _ = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate(timeout=20)
    return output or ""


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="rvm05-selfcheck-"))
    registry = tmp / "data" / "known_faces.json"

    # -- 1. a fresh installation, analysis on, models warmed up --------------
    process, base = start(registry, tmp)
    try:
        deadline = time.monotonic() + 60.0
        status = {}
        while time.monotonic() < deadline:
            status = http("GET", base + "/api/status")[1]
            if status.get("analysis", {}).get("ready"):
                break
            time.sleep(0.2)
        check("analysis reported ready before the probe registered",
              bool(status.get("analysis", {}).get("ready")),
              f"features={status.get('analysis')}")
        check("the picture pump is running", status.get("frames", 0) >= 3,
              f"frames={status.get('frames')}")

        # The generated scene has no person in it, so the honest answer is a
        # refusal; what this records is which refusal and whether it stayed
        # clean.  A 201 here would mean a face was invented, which the file
        # then has to contain.  ``samples-missing`` only means the three
        # analysed frames are not there yet, so it is retried.
        deadline = time.monotonic() + 20.0
        while True:
            code, body = http("POST", base + "/api/faces/known", {"name": "Machine Probe"})
            if body.get("reason") != "samples-missing" or time.monotonic() > deadline:
                break
            time.sleep(0.3)
        if code == 201:
            check("registering a face on the generated scene wrote the file",
                  registry.exists() and "Machine Probe" in json.loads(registry.read_text())["faces"],
                  f"status={code} body={body} registry={registry.exists()}")
        else:
            check("registering with no face in view is refused and writes nothing",
                  code == 409 and body.get("reason") == "no-face" and not registry.exists(),
                  f"status={code} body={body} registry_exists={registry.exists()}")

        check("the same server still answers after the refusal",
              http("GET", base + "/api/status")[0] == 200
              and http("GET", base + "/api/faces/known")[1] == {"known": []},
              f"known={http('GET', base + '/api/faces/known')[1]}")
        code, body = http("DELETE", base + "/api/faces/known/Nobody")
        check("forgetting an unknown name is a 404 with the contract body",
              code == 404 and body.get("reason") == "bad-name", f"status={code} body={body}")
    finally:
        log = stop(process)
    check("the server shut down without a traceback", "Traceback" not in log, log[-200:])

    # -- 2. a seeded registry: survives a restart, deletion reaches the disk --
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"version": 1, "faces": {"Alice Ng": [0.25] * 1434}}), encoding="utf-8")
    process, base = start(registry, tmp)
    try:
        check("--known-faces list is served by the first process",
              http("GET", base + "/api/faces/known")[1] == {"known": ["Alice Ng"]},
              f"known={http('GET', base + '/api/faces/known')[1]}")
    finally:
        stop(process)

    process, base = start(registry, tmp)
    try:
        check("a second process serves the same list",
              http("GET", base + "/api/faces/known")[1] == {"known": ["Alice Ng"]},
              f"known={http('GET', base + '/api/faces/known')[1]}")
        code, body = http("DELETE", base + "/api/faces/known/Alice%20Ng")
        check("DELETE answers with the contract body",
              code == 200 and body == {"removed": True, "known": []}, f"status={code} body={body}")
        on_disk = json.loads(registry.read_text(encoding="utf-8"))["faces"]
        check("the deletion reached the file before the reply", on_disk == {}, f"disk faces={on_disk}")
    finally:
        stop(process)

    process, base = start(registry, tmp)
    try:
        check("a third process starts from the emptied file",
              http("GET", base + "/api/faces/known")[1] == {"known": []},
              f"known={http('GET', base + '/api/faces/known')[1]}")
    finally:
        stop(process)

    print(f"\n{sum(1 for r in results if r[0] == 'PASS')} passed, "
          f"{sum(1 for r in results if r[0] == 'FAIL')} failed")
    print(f"workdir: {tmp}")
    return 1 if any(r[0] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
