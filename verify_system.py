"""End-to-end check: start the real server, exercise it, save evidence."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "_verify"
OUT.mkdir(exist_ok=True)
PORT = 8123
FPS = 25.0
WIDTH, HEIGHT = 320, 240
BASE = f"http://127.0.0.1:{PORT}"


async def wait_for_server(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    async with aiohttp.ClientSession() as client:
        while time.time() < deadline:
            try:
                async with client.get(f"{BASE}/api/status") as response:
                    if response.status == 200:
                        return True
            except aiohttp.ClientError:
                pass
            await asyncio.sleep(0.25)
    return False


async def exercise() -> dict:
    results: dict[str, object] = {}
    async with aiohttp.ClientSession() as client:
        async with client.get(f"{BASE}/") as response:
            html = await response.text()
            results["index"] = {
                "status": response.status,
                "bytes": len(html),
                "has_title": "Remote Video Monitor" in html,
                "has_canvas": 'id="spark"' in html,
            }

        for asset in ("app.js", "style.css"):
            async with client.get(f"{BASE}/static/{asset}") as response:
                body = await response.text()
                results[f"static/{asset}"] = {"status": response.status, "bytes": len(body)}

        # Let the pipeline produce a few pictures.
        for _ in range(40):
            async with client.get(f"{BASE}/api/status") as response:
                status = await response.json()
            if status.get("frames", 0) >= 4:
                break
            await asyncio.sleep(0.25)

        results["status"] = status

        async with client.get(f"{BASE}/api/snapshot.jpg") as response:
            jpeg = await response.read()
            (OUT / "snapshot.jpg").write_bytes(jpeg)
            results["snapshot"] = {
                "status": response.status,
                "bytes": len(jpeg),
                "is_jpeg": jpeg[:2] == b"\xff\xd8",
                "content_type": response.headers.get("Content-Type"),
            }

        async with client.get(f"{BASE}/api/snapshot.jpg?view=decoded") as response:
            decoded = await response.read()
            (OUT / "snapshot-decoded.jpg").write_bytes(decoded)
            results["snapshot_decoded"] = {
                "status": response.status,
                "bytes": len(decoded),
                "is_jpeg": decoded[:2] == b"\xff\xd8",
                "differs_from_source": decoded != jpeg,
            }

        # The dashboard is only useful if the server answers while it is
        # coding, so the latency of the status endpoint is measured with the
        # pipeline running rather than on an idle server.
        latencies: list[float] = []
        for _ in range(20):
            started = time.perf_counter()
            async with client.get(f"{BASE}/api/status") as response:
                await response.read()
            latencies.append((time.perf_counter() - started) * 1000.0)
        latencies.sort()
        results["api_latency_ms"] = {
            "median": round(latencies[len(latencies) // 2], 1),
            "worst": round(latencies[-1], 1),
        }

        async with client.get(f"{BASE}/api/stream.mjpg", timeout=aiohttp.ClientTimeout(total=6)) as response:
            chunk = await response.content.read(4096)
            results["mjpeg"] = {
                "status": response.status,
                "content_type": response.headers.get("Content-Type"),
                "saw_boundary": b"--frame" in chunk,
            }

        async with client.post(f"{BASE}/api/config", json={"bitrate": 800_000}) as response:
            body = await response.json()
            results["config"] = {"status": response.status, "bitrate_target": body["bitrate_target"]}

        async with client.post(f"{BASE}/api/record", json={"recording": True}) as response:
            body = await response.json()
            started = body["recording"]
        await asyncio.sleep(1.0)
        async with client.post(f"{BASE}/api/record", json={"recording": False}) as response:
            body = await response.json()
            stopped = body["recording"]
        results["record"] = {"started": started, "stopped": stopped}

        async with client.ws_connect(f"{BASE.replace('http', 'ws')}/ws") as socket:
            first = await asyncio.wait_for(socket.receive_json(), timeout=10)
            second = await asyncio.wait_for(socket.receive_json(), timeout=10)
            results["websocket"] = {
                "messages": 2,
                "bitrate": first.get("bitrate"),
                "advanced": second.get("packets_sent", 0) >= first.get("packets_sent", 0),
                "clients": first.get("clients"),
            }

        async with client.get(f"{BASE}/api/clips") as response:
            body = await response.json()
            results["clips"] = {"count": body["count"], "paths": body["clips"]}

    (OUT / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return results


def main() -> int:
    async def run() -> int:
        # The application is hosted in this process with an explicit runner --
        # the same path the command line entry point uses. A child process
        # cannot bind a socket in this environment, and hosting in-process
        # exercises the identical application object, routes and WebSocket.
        from aiohttp import web

        from rvm.server.app import create_app

        app = create_app(
            width=WIDTH,
            height=HEIGHT,
            fps=FPS,
            bitrate=1_200_000,
            prefer_camera=False,
            record_dir=str(OUT / "recordings"),
        )

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", PORT)
        await site.start()
        print(f"serving on {BASE}", flush=True)

        try:
            results = await exercise()
            print(json.dumps(results, indent=2, default=str))
            return 0
        finally:
            await runner.cleanup()

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())