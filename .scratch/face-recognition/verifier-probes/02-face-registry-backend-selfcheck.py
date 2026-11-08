#!/usr/bin/env python3
"""Live probe for the face registry: does a registration request disturb the stream?

Start the server exactly as the acceptance ticket says, then run this:

    .venv\\Scripts\\python.exe run_server.py --no-camera --port 8099
    .venv\\Scripts\\python.exe .scratch/face-recognition/verifier-probes/02-face-registry-backend-selfcheck.py

It measures three things against the *running* server, with no test client in
the way:

* ``/api/status`` latency before, during and after a burst of registration
  requests (the burst is what "registration must not block the event loop"
  means in practice);
* how many MJPEG pictures ``/api/stream.mjpg`` serves in the same windows (a
  blocked loop stops the picture, not just the JSON);
* what the registrations answered, and whether any list file appeared.

The generated scene has no face, so a burst of registrations must all be
``409 no-face`` and must write nothing: that is the "zero writes on the failure
path" half of the contract, observed on the real machine.
"""

from __future__ import annotations

import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8099"
LIST_FILE = Path("data") / "known_faces.json"
WINDOW = 4.0


def get_json(path: str):
    with urllib.request.urlopen(BASE + path, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def post_json(path: str, payload: dict):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def wait_until_ready(timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            _, status = get_json("/api/status")
        except Exception as exc:  # noqa: BLE001 - the server may not be up yet
            last = exc
            time.sleep(0.25)
            continue
        if status.get("analysis", {}).get("ready"):
            return status
        last = status.get("analysis")
        time.sleep(0.25)
    raise SystemExit(f"analysis never became ready: {last!r}")


def sample_status(seconds: float, interval: float = 0.05) -> list[float]:
    """Time each ``/api/status`` round trip for *seconds*."""
    latencies: list[float] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        started = time.monotonic()
        get_json("/api/status")
        latencies.append((time.monotonic() - started) * 1000.0)
        time.sleep(interval)
    return latencies


def count_mjpeg_frames(seconds: float) -> int:
    """Count the multipart boundaries ``/api/stream.mjpg`` serves in *seconds*."""
    frames = 0
    deadline = time.monotonic() + seconds
    with urllib.request.urlopen(BASE + "/api/stream.mjpg", timeout=15) as response:
        tail = b""
        while time.monotonic() < deadline:
            chunk = response.read(65536)
            if not chunk:
                break
            frames += (tail + chunk).count(b"--frame")
            tail = chunk[-8:]
    return frames


def summarise(name: str, values: list[float]) -> str:
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return (
        f"{name}: n={len(ordered)} median={statistics.median(ordered):.1f}ms "
        f"p95={p95:.1f}ms max={ordered[-1]:.1f}ms"
    )


def main() -> int:
    status = wait_until_ready()
    analysis = status.get("analysis", {})
    print(f"source={status.get('source')} frames={status.get('frames')}")
    print(
        f"analysis: enabled={analysis.get('enabled')} ready={analysis.get('ready')} "
        f"face_recognition={analysis.get('face_recognition')}"
    )
    print(f"list file before: {LIST_FILE} exists={LIST_FILE.exists()}")

    baseline_latency = sample_status(2.0)
    baseline_frames = count_mjpeg_frames(2.0)

    outcomes: list[tuple[int, str | None]] = []
    outcomes_lock = threading.Lock()
    stop = threading.Event()

    def register(worker: int) -> None:
        index = 0
        while not stop.is_set():
            code, body = post_json("/api/faces/known", {"name": f"probe-{worker}-{index}"})
            with outcomes_lock:
                outcomes.append((code, body.get("reason")))
            index += 1

    during_status: dict = {}
    during_mjpeg: dict = {}

    def sample_during() -> None:
        started = time.monotonic()
        during_status["latencies"] = sample_status(WINDOW)
        during_status["seconds"] = time.monotonic() - started

    def count_during() -> None:
        started = time.monotonic()
        during_mjpeg["frames"] = count_mjpeg_frames(WINDOW)
        during_mjpeg["seconds"] = time.monotonic() - started

    sampler = threading.Thread(target=sample_during)
    counter = threading.Thread(target=count_during)
    sampler.start()
    counter.start()
    burst_started = time.monotonic()
    workers = [threading.Thread(target=register, args=(worker,)) for worker in range(4)]
    for worker in workers:
        worker.start()
    # Keep registering for the whole measurement window, so the status and
    # MJPEG readings overlap continuous inference rather than a single burst.
    time.sleep(WINDOW)
    stop.set()
    for worker in workers:
        worker.join()
    burst_seconds = time.monotonic() - burst_started

    sampler.join()
    counter.join()

    after_latency = sample_status(2.0)
    after_frames = count_mjpeg_frames(2.0)

    print(summarise("status baseline (idle)", baseline_latency))
    print(summarise("status during burst", during_status["latencies"]))
    print(summarise("status after burst", after_latency))
    print(
        f"mjpeg baseline: {baseline_frames} frames in 2.0s "
        f"({baseline_frames / 2.0:.1f} fps)"
    )
    frames = during_mjpeg["frames"]
    seconds = during_mjpeg["seconds"]
    print(f"mjpeg during burst: {frames} frames in {seconds:.2f}s ({frames / seconds:.1f} fps)")
    print(f"mjpeg after burst: {after_frames} frames in 2.0s ({after_frames / 2.0:.1f} fps)")
    print(f"registration burst: {len(outcomes)} requests in {burst_seconds:.2f}s")
    counts: dict[str, int] = {}
    for code, reason in outcomes:
        counts[f"{code} {reason}"] = counts.get(f"{code} {reason}", 0) + 1
    print("registration outcomes: " + ", ".join(f"{key} x{value}" for key, value in sorted(counts.items())))

    code, body = get_json("/api/faces/known")
    print(f"GET /api/faces/known -> {code} {json.dumps(body)}")
    code, body = post_json("/api/faces/known", {"name": ""})
    print(f"POST empty name -> {code} {json.dumps(body)}")
    print(f"list file after burst: exists={LIST_FILE.exists()}")

    request = urllib.request.Request(BASE + "/api/faces/known/Nobody", method="DELETE")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(f"DELETE unknown -> {response.status}")
    except urllib.error.HTTPError as error:
        print(f"DELETE unknown -> {error.code} {error.read().decode('utf-8')}")

    with urllib.request.urlopen(BASE + "/api/snapshot.jpg", timeout=5) as response:
        print(f"snapshot: {response.status} {response.headers.get('Content-Type')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
