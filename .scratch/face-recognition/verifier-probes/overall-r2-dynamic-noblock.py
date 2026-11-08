#!/usr/bin/env python3
"""overall-r2-dynamic non-blocking probe.

While a real ``POST /api/faces/known`` is in flight against the stub server
(``sample_delay`` makes each of the three sampling calls slow), this probe:

- polls ``GET /api/status`` as fast as possible and records the largest gap
  between consecutive successful responses;
- concurrently reads bytes off the real MJPEG ``/api/stream.mjpg`` to prove the
  stream keeps producing during registration;
- records the POST's elapsed time and status code.

    python overall-r2-dynamic-noblock.py --port 8150 --name "Slow Person"
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import urllib.request


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8150)
    ap.add_argument("--name", default="Slow Person")
    ap.add_argument("--mjpeg-bytes", type=int, default=40000)
    args = ap.parse_args()
    base = f"http://127.0.0.1:{args.port}"

    stop = threading.Event()
    gaps = []
    polls = [0]
    mjpeg = [0]
    last = [time.monotonic()]

    def poll_status() -> None:
        while not stop.is_set():
            try:
                with urllib.request.urlopen(base + "/api/status", timeout=5) as r:
                    r.read()
                now = time.monotonic()
                gaps.append(now - last[0])
                last[0] = now
                polls[0] += 1
            except Exception as exc:  # noqa: BLE001
                gaps.append(("ERR", str(exc)))
                time.sleep(0.05)

    def read_mjpeg() -> None:
        try:
            with urllib.request.urlopen(base + "/api/stream.mjpg", timeout=10) as r:
                while not stop.is_set() and mjpeg[0] < args.mjpeg_bytes:
                    chunk = r.read(8192)
                    if not chunk:
                        break
                    mjpeg[0] += len(chunk)
        except Exception as exc:  # noqa: BLE001
            mjpeg.append("ERR " + str(exc))

    t_poll = threading.Thread(target=poll_status, daemon=True)
    t_mjpeg = threading.Thread(target=read_mjpeg, daemon=True)
    t_poll.start()
    t_mjpeg.start()

    body = json.dumps({"name": args.name}).encode()
    req = urllib.request.Request(
        base + "/api/faces/known", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            code, payload = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        code, payload = e.code, e.read().decode()
    elapsed = time.monotonic() - t0
    stop.set()
    t_poll.join(timeout=3)
    t_mjpeg.join(timeout=3)

    real_gaps = [g for g in gaps if not isinstance(g, tuple)]
    errs = [g for g in gaps if isinstance(g, tuple)]
    print(f"POST took {elapsed*1000:.0f} ms -> {code} {payload.strip()}")
    print(f"status polls {polls[0]}, max gap {max(real_gaps):.3f}s, errors {errs}")
    print(f"mjpeg bytes {mjpeg[0]}{' ' + mjpeg[1] if len(mjpeg) > 1 else ''}")


if __name__ == "__main__":
    main()
