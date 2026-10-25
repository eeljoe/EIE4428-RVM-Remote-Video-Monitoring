"""End-to-end tests for the HTTP and WebSocket surface."""

import asyncio
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer

from rvm.server.app import create_app
from rvm.server.session import StreamSession


@pytest.fixture
async def client(tmp_path):
    session = StreamSession(
        width=160,
        height=96,
        fps=10.0,
        bitrate=300_000,
        record_dir=tmp_path / "clips",
    )
    app = create_app(session=session)
    test_client = TestClient(TestServer(app))
    await test_client.start_server()
    try:
        yield test_client
    finally:
        await test_client.close()


async def wait_for_picture(client, attempts=60):
    """Let the capture pump produce at least one picture."""
    for _ in range(attempts):
        response = await client.get("/api/snapshot.jpg")
        if response.status == 200:
            return response
        await asyncio.sleep(0.05)
    return await client.get("/api/snapshot.jpg")


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------


async def test_index_page_is_served(client):
    response = await client.get("/")

    assert response.status == 200
    assert "Remote Video Monitor" in await response.text()


async def test_stylesheet_is_served(client):
    response = await client.get("/static/style.css")

    assert response.status == 200
    assert "layout" in await response.text()


async def test_client_script_is_served(client):
    response = await client.get("/static/app.js")

    assert response.status == 200
    assert "connect" in await response.text()


# --------------------------------------------------------------------------
# Telemetry
# --------------------------------------------------------------------------


async def test_status_endpoint_reports_stream_health(client):
    response = await client.get("/api/status")
    body = await response.json()

    assert response.status == 200
    assert body["width"] == 160
    assert body["height"] == 96
    assert "qp" in body


async def test_status_endpoint_is_valid_json(client):
    response = await client.get("/api/status")

    json.loads(await response.text())


async def test_snapshot_endpoint_returns_a_jpeg(client):
    response = await wait_for_picture(client)

    assert response.status == 200
    assert response.headers["Content-Type"] == "image/jpeg"
    assert (await response.read())[:2] == b"\xff\xd8"


async def test_snapshot_is_not_cached(client):
    response = await client.get("/api/snapshot.jpg")

    assert "no-store" in response.headers.get("Cache-Control", "")


async def test_metrics_endpoint_offers_a_download(client):
    response = await client.get("/api/metrics")

    assert response.status == 200
    assert "attachment" in response.headers["Content-Disposition"]


async def test_clips_endpoint_lists_recordings(client):
    empty = await (await client.get("/api/clips")).json()
    assert empty["count"] == 0

    await (await client.post("/api/record", json={"recording": True})).json()
    # Wait until the pump has actually written a frame rather than sleeping a
    # fixed time: on a loaded machine a fixed window can be missed.
    for _ in range(60):
        if (await (await client.get("/api/clips")).json())["count"] == 1:
            break
        await asyncio.sleep(0.05)
    await (await client.post("/api/record", json={"recording": False})).json()

    listed = await (await client.get("/api/clips")).json()

    assert listed["count"] == 1
    assert listed["clips"][0]["frames"] >= 1


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------


async def test_config_endpoint_changes_the_target_bitrate(client):
    response = await client.post(
        "/api/config", json={"bitrate": 900_000, "gop_size": 15}
    )
    body = await response.json()

    assert response.status == 200
    assert body["bitrate_target"] == 900_000


async def test_config_endpoint_rejects_an_invalid_bitrate(client):
    response = await client.post("/api/config", json={"bitrate": -5})

    assert response.status == 400


async def test_record_endpoint_toggles_recording(client):
    started = await (await client.post("/api/record", json={"recording": True})).json()
    assert started["recording"] is True

    stopped = await (await client.post("/api/record", json={"recording": False})).json()
    assert stopped["recording"] is False


# --------------------------------------------------------------------------
# WebSocket
# --------------------------------------------------------------------------


async def test_websocket_pushes_telemetry(client):
    socket = await client.ws_connect("/ws")
    try:
        message = await asyncio.wait_for(socket.receive_json(), timeout=5.0)
        assert "bitrate" in message
    finally:
        await socket.close()


async def test_websocket_client_is_registered_while_connected(client):
    socket = await client.ws_connect("/ws")
    try:
        await asyncio.wait_for(socket.receive_json(), timeout=5.0)
        status = await (await client.get("/api/status")).json()
        assert status["clients"] >= 1
    finally:
        await socket.close()


async def test_websocket_delivers_coded_packets(client):
    """The custom codec's packets are observable, not just JPEG."""
    socket = await client.ws_connect("/ws")
    try:
        # Drain telemetry until the capture pump has produced packets.
        for _ in range(40):
            status = await (await client.get("/api/status")).json()
            if status["packets_sent"] > 0:
                break
            await asyncio.sleep(0.05)

        status = await (await client.get("/api/status")).json()
        assert status["packets_sent"] > 0
    finally:
        await socket.close()