"""HTTP and WebSocket application exposing the monitoring system.

Routes
------
``GET  /``                     the operator's browser view
``GET  /api/status``           live JSON telemetry
``GET  /api/snapshot.jpg``     the current picture
``GET  /api/stream.mjpg``      continuous MJPEG video
``GET  /api/clips``            recordings made so far
``GET  /api/clips/<c>/<n>.jpg`` one stored frame, for previewing a clip
``POST /api/motion``           confine detection to a region / pick sensitivity
``POST /api/config``           change the encoder operating point
``POST /api/record``           start or stop a clip
``GET  /api/metrics``          download the current telemetry as JSON
``WS   /ws``                   telemetry push plus the live packet feed

A browser cannot decode the project's custom RVM1 bitstream, so the *picture*
path is MJPEG and JPEG snapshots.  The custom codec is what carries the
efficient transport path, and ``/ws`` exposes those real RTP packets so the
packetisation, jitter and statistics can be observed in the browser rather
than only asserted in tests.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from aiohttp import WSMsgType, web

from ..network.packet import Packet
from .session import StreamSession
from .source import open_source

__all__ = ["build_app", "create_app", "main"]

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

# Typed application keys. aiohttp prefers these over plain strings so a typo in
# a key name is a type error at the point of use rather than a KeyError later.
SESSION = web.AppKey("session", StreamSession)
STOP = web.AppKey("stop", asyncio.Event)
PUMP = web.AppKey("pump", asyncio.Task)


def create_app(
    width: int = 320,
    height: int = 240,
    fps: float = 15.0,
    bitrate: int = 1_200_000,
    camera_index: int = 0,
    prefer_camera: bool = True,
    record_dir: str | Path = "recordings",
    session: StreamSession | None = None,
) -> web.Application:
    """Build the application and its single shared :class:`StreamSession`."""
    if session is None:
        session = StreamSession(
            width=width,
            height=height,
            fps=fps,
            bitrate=bitrate,
            source=open_source(
                prefer_camera=prefer_camera,
                camera_index=camera_index,
                width=width,
                height=height,
                fps=fps,
            ),
            record_dir=record_dir,
        )

    app = web.Application()
    app[SESSION] = session
    app[STOP] = asyncio.Event()
    app.router.add_get("/", index)
    app.router.add_static("/static", WEB_ROOT, name="static")
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/snapshot.jpg", handle_snapshot)
    app.router.add_get("/api/stream.mjpg", handle_mjpeg)
    app.router.add_get("/api/clips", handle_clips)
    app.router.add_get("/api/clips/{clip}/{frame}.jpg", handle_clip_frame)
    app.router.add_get("/api/metrics", handle_metrics)
    app.router.add_post("/api/config", handle_config)
    app.router.add_post("/api/motion", handle_motion)
    app.router.add_post("/api/record", handle_record)
    app.router.add_get("/ws", handle_websocket)

    app.on_startup.append(_startup)
    app.on_cleanup.append(_cleanup)
    return app


# --------------------------------------------------------------------------
# Pages and simple GETs
# --------------------------------------------------------------------------


async def index(request: web.Request) -> web.Response:
    return web.FileResponse(WEB_ROOT / "index.html")


def _view(request: web.Request) -> str:
    """Which picture the client asked for: the raw source or the decoded one.

    An unknown value falls back to the source rather than raising, because the
    parameter is cosmetic: a mistyped query string should still show a picture.
    """
    return "decoded" if request.query.get("view", "").lower() == "decoded" else "source"


async def handle_status(request: web.Request) -> web.Response:
    session: StreamSession = request.app[SESSION]
    return web.json_response(session.status())


async def handle_snapshot(request: web.Request) -> web.Response:
    session: StreamSession = request.app[SESSION]
    view = _view(request)
    jpeg = session.snapshot_jpeg(view=view)
    if jpeg is None:
        # The first picture takes a moment to appear after the server starts;
        # waiting for it briefly is friendlier than refusing the request.
        jpeg = await session.wait_for_picture(view=view, timeout=2.0)
    if jpeg is None:
        raise web.HTTPServiceUnavailable(text="no picture captured yet")
    return web.Response(
        body=jpeg,
        headers={
            "Content-Type": "image/jpeg",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


async def handle_metrics(request: web.Request) -> web.Response:
    session: StreamSession = request.app[SESSION]
    payload = json.dumps(session.status(), indent=2).encode("utf-8")
    return web.Response(
        body=payload,
        headers={
            "Content-Type": "application/json",
            "Content-Disposition": 'attachment; filename="rvm-metrics.json"',
        },
    )


async def handle_clips(request: web.Request) -> web.Response:
    session: StreamSession = request.app[SESSION]
    root = Path(session.record_dir)

    # Frames are named "<clip-start>_<index>.jpg", so a clip is recovered by
    # its prefix rather than by a directory: that keeps a clip contiguous even
    # if two recordings are started back to back.
    clips: dict[str, int] = {}
    for path in root.glob("*.jpg"):
        clips[path.stem.rsplit("_", 1)[0]] = clips.get(
            path.stem.rsplit("_", 1)[0], 0
        ) + 1

    return web.json_response(
        {
            "clips": [
                {"name": name, "frames": frames}
                for name, frames in sorted(clips.items())
            ],
            "count": len(clips),
        }
    )


#: Clip names are produced by :class:`FrameRecorder` and by nothing else, so the
#: route accepts exactly that shape.  Anything else is refused instead of being
#: joined onto the recordings directory -- a name is user input, and joining it
#: is how a preview endpoint becomes a file-disclosure bug.
_CLIP_NAME = re.compile(r"^\d{8}_\d{6}$")


async def handle_clip_frame(request: web.Request) -> web.Response:
    session: StreamSession = request.app[SESSION]
    clip = request.match_info["clip"]
    frame = request.match_info["frame"]
    if not _CLIP_NAME.match(clip) or not frame.isdigit():
        raise web.HTTPNotFound()

    path = Path(session.record_dir) / f"{clip}_{int(frame):06d}.jpg"
    if not path.is_file():
        raise web.HTTPNotFound()

    return web.FileResponse(
        path, headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
    )


# --------------------------------------------------------------------------
# MJPEG stream
# --------------------------------------------------------------------------


async def handle_mjpeg(request: web.Request) -> web.StreamResponse:
    session: StreamSession = request.app[SESSION]
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
            "Connection": "close",
        },
    )
    await response.prepare(request)

    boundary = b"--frame"
    last = b""
    view = _view(request)
    try:
        while True:
            transport = request.transport
            if transport is None or transport.is_closing():
                break

            jpeg = session.snapshot_jpeg(view=view)
            if jpeg and jpeg != last:
                last = jpeg
                await response.write(
                    boundary
                    + b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                    + jpeg
                    + b"\r\n"
                )
            await asyncio.sleep(1.0 / max(session.fps, 1.0) / 2.0)
    except (asyncio.CancelledError, ConnectionResetError):
        pass

    return response


# --------------------------------------------------------------------------
# POSTs
# --------------------------------------------------------------------------


async def handle_config(request: web.Request) -> web.Response:
    session: StreamSession = request.app[SESSION]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text="expected a JSON body")

    try:
        session.update_config(
            bitrate=body.get("bitrate"), gop_size=body.get("gop_size")
        )
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))

    return web.json_response(session.status())


async def handle_motion(request: web.Request) -> web.Response:
    """Confine motion detection to a region and/or choose how eager it is.

    Both settings answer the same question -- what should count as an event --
    so they share one endpoint and one round trip.  A key that is present but
    ``null`` means "clear", which is different from omitting the key, so the
    body is inspected rather than read with defaults.
    """
    session: StreamSession = request.app[SESSION]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text="expected a JSON body")
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="expected a JSON object")

    try:
        if "roi" in body:
            session.set_roi(body["roi"])
        if "sensitivity" in body:
            session.set_motion_sensitivity(body["sensitivity"])
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))

    return web.json_response(session.status())


async def handle_record(request: web.Request) -> web.Response:
    session: StreamSession = request.app[SESSION]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text="expected a JSON body")

    enabled = bool(body.get("recording", False))
    session.configure_recording(enabled)

    return web.json_response({"recording": session.recording, **session.status()})


# --------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    session: StreamSession = request.app[SESSION]
    client = session.add_client()
    socket = web.WebSocketResponse(heartbeat=20.0)
    await socket.prepare(request)

    try:
        async def push_telemetry() -> None:
            while not socket.closed:
                await socket.send_json(session.status())
                await asyncio.sleep(0.5)

        telemetry = asyncio.create_task(push_telemetry())

        async for message in socket:
            if message.type != WSMsgType.TEXT:
                if message.type == WSMsgType.ERROR:
                    break
                continue

            if message.data == "close":
                break

            # Delivery feedback is the RTCP loop: the receiver tells the
            # sender what actually arrived, and the encoder reacts to it.
            if message.data.startswith("{"):
                try:
                    session.record_feedback(json.loads(message.data))
                except (ValueError, TypeError):
                    pass

        telemetry.cancel()
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        session.remove_client(client.id)

    return socket


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


async def _startup(app: web.Application) -> None:
    session: StreamSession = app[SESSION]
    app[PUMP] = asyncio.create_task(session.run_forever(app[STOP]))


async def _cleanup(app: web.Application) -> None:
    app[STOP].set()
    pump = app.get(PUMP)
    if pump is not None:
        pump.cancel()
        try:
            await pump
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    app[SESSION].close()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def build_app(**kwargs) -> web.Application:
    return create_app(**kwargs)


def main(argv: list[str] | None = None) -> None:  # pragma: no cover - CLI shim
    import argparse

    parser = argparse.ArgumentParser(description="EIE4428 Remote Video Monitor")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--bitrate", type=int, default=1_200_000)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument(
        "--no-camera",
        action="store_true",
        help="use the generated scene instead of a webcam",
    )
    parser.add_argument("--recordings", default="recordings")
    args = parser.parse_args(argv)

    # The runner is driven explicitly rather than through web.run_app, which
    # installs console signal handlers that misbehave when the process is
    # started detached from a terminal. The application is also built inside
    # the running loop so its Event and Lock objects belong to it.
    async def serve() -> None:
        app = create_app(
            width=args.width,
            height=args.height,
            fps=args.fps,
            bitrate=args.bitrate,
            camera_index=args.camera,
            prefer_camera=not args.no_camera,
            record_dir=args.recordings,
        )

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, args.host, args.port)
        await site.start()

        source = app[SESSION].source.name
        print(
            f"RVM serving on http://{args.host}:{args.port}/  "
            f"({args.width}x{args.height} @ {args.fps:g} fps, source: {source})",
            flush=True,
        )
        print("Press Ctrl+C to stop.", flush=True)

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await runner.cleanup()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":  # pragma: no cover
    main()