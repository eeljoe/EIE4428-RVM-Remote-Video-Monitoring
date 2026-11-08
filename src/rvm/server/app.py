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
``GET  /api/faces/known``      the registered face names
``POST /api/faces/known``      register a face from the recent analysis frames
``DELETE /api/faces/known/{name}``  forget a registered face
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
import typing
from pathlib import Path

from aiohttp import WSMsgType, web

from ..analysis.face_store import DEFAULT_KNOWN_FACES
from ..network.packet import Packet
from .session import FaceRequestError, StreamSession
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
    analysis: bool = False,
    analysis_interval: float = 0.5,
    known_faces: str | Path | None = None,
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
            analysis=analysis,
            analysis_interval=analysis_interval,
            known_faces=known_faces,
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
    app.router.add_get("/api/features", handle_features)
    app.router.add_get("/api/tracks", handle_tracks)
    app.router.add_get("/api/faces/identities", handle_face_identities)
    app.router.add_get("/api/faces/known", handle_known_faces)
    app.router.add_post("/api/faces/known", handle_register_face)
    app.router.add_delete("/api/faces/known/{name}", handle_forget_face)
    app.router.add_get("/api/emotions", handle_emotions)
    app.router.add_get("/api/gestures", handle_gestures)
    app.router.add_get("/api/audio/events", handle_audio_events)
    app.router.add_post("/api/audio/control", handle_audio_control)
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
    if not _CLIP_NAME.match(clip) or not (frame.isascii() and frame.isdigit()):
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
# Optional analysis
# --------------------------------------------------------------------------


async def handle_features(request: web.Request) -> web.Response:
    """Which optional analysers this machine can run."""
    session: StreamSession = request.app[SESSION]
    return web.json_response(session.features())


async def handle_tracks(request: web.Request) -> web.Response:
    """Tracked objects with their persistent IDs."""
    session: StreamSession = request.app[SESSION]
    return web.json_response(session.analysis_status()["tracks"])


async def handle_face_identities(request: web.Request) -> web.Response:
    """Faces recognised against the (possibly empty) known-face database."""
    session: StreamSession = request.app[SESSION]
    return web.json_response(session.analysis_status()["face_identities"])


#: Statuses the face endpoints may answer with, and the exception class that
#: carries each one.  Raised rather than returned so the failure is shaped in
#: one place whether it comes from validation or from a worker thread.
_CONTRACT_ERRORS = {
    400: web.HTTPBadRequest,
    404: web.HTTPNotFound,
    409: web.HTTPConflict,
    500: web.HTTPInternalServerError,
    503: web.HTTPServiceUnavailable,
}


def _fail(status: int, reason: str, message: str) -> typing.NoReturn:
    """Refuse a face request with the contract's ``{"error", "reason"}`` body.

    Every failure is JSON with an enumerated ``reason``, because the panel has
    to tell the operator *why* nothing happened: "no face in view" and "the
    models are still loading" need different actions, and a bare status code
    cannot say which.
    """
    raise _CONTRACT_ERRORS[status](
        text=json.dumps({"error": message, "reason": reason}),
        content_type="application/json",
    )


async def handle_known_faces(request: web.Request) -> web.Response:
    """The registered face names."""
    session: StreamSession = request.app[SESSION]
    return web.json_response({"known": session.known_face_names()})


async def handle_register_face(request: web.Request) -> web.Response:
    """Register a face from the last few analysed frames."""
    session: StreamSession = request.app[SESSION]
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - malformed body is a client error
        _fail(400, "bad-name", "expected a JSON body with a name")
    if not isinstance(body, dict):
        _fail(400, "bad-name", "expected a JSON object with a name")

    # Sampling runs landmarker inference on stored frames: a worker thread, so
    # the stream and the telemetry keep being served while it works.
    try:
        result = await asyncio.to_thread(session.register_face, body.get("name"))
    except FaceRequestError as exc:
        _fail(exc.status, exc.reason, exc.message)

    return web.json_response(result, status=201)


async def handle_forget_face(request: web.Request) -> web.Response:
    """Forget a registered face; the list is written before this answers."""
    session: StreamSession = request.app[SESSION]
    try:
        result = await asyncio.to_thread(session.remove_face, request.match_info["name"])
    except FaceRequestError as exc:
        _fail(exc.status, exc.reason, exc.message)

    return web.json_response(result)


async def handle_emotions(request: web.Request) -> web.Response:
    """Classified facial expressions."""

    session: StreamSession = request.app[SESSION]
    return web.json_response(session.analysis_status()["emotions"])


async def handle_gestures(request: web.Request) -> web.Response:
    """Classified hand gestures."""
    session: StreamSession = request.app[SESSION]
    return web.json_response(session.analysis_status()["gestures"])


async def handle_audio_events(request: web.Request) -> web.Response:
    """Recent acoustic events, newest last."""
    session: StreamSession = request.app[SESSION]
    return web.json_response(session.analysis_status()["audio"])


async def handle_audio_control(request: web.Request) -> web.Response:
    """Start or stop microphone monitoring."""
    session: StreamSession = request.app[SESSION]
    try:
        body = await request.json()
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text="expected a JSON body")
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        raise web.HTTPBadRequest(text='expected {"enabled": true|false}')

    requested = body["enabled"]
    # Opening a sound device takes hundreds of milliseconds, and so does asking
    # whether one exists; both belong on a worker thread, not on the loop.
    report = await asyncio.to_thread(session.audio_report, requested)
    return web.json_response(report)


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


def _opencv_distributions() -> list[str]:
    """The OpenCV distributions installed alongside each other, sorted.

    They all own a ``cv2`` directory, so two of them fight over the same files:
    whichever installs last wins, and uninstalling either one deletes files the
    survivor's RECORD still claims.  Pip does not warn.  This is worth one line
    at start-up because the failure it causes (a broken ``cv2`` import) does
    not look like a packaging problem.
    """
    from importlib.metadata import distributions

    known = {
        "opencv-python",
        "opencv-python-headless",
        "opencv-contrib-python",
        "opencv-contrib-python-headless",
    }
    found = {
        str(dist.metadata["Name"]).lower()
        for dist in distributions()
        if str(dist.metadata["Name"] or "").lower() in known
    }
    return sorted(found)


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
    parser.add_argument(
        "--known-faces",
        default=str(DEFAULT_KNOWN_FACES),
        help="JSON file holding the registered face names and embeddings",
    )
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="skip the optional face / gesture / audio analysers",
    )
    args = parser.parse_args(argv)

    duplicates = _opencv_distributions()
    if len(duplicates) > 1:
        print(
            "warning: several OpenCV distributions are installed "
            f"({', '.join(duplicates)}); they all own the cv2 directory and can "
            "corrupt each other. Keep exactly one: uninstall the headless build "
            "FIRST, then install requirements-analysis.txt, so contrib is the "
            "single provider.",
            flush=True,
        )

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
            analysis=not args.no_analysis,
            known_faces=args.known_faces,
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