"""End-to-end tests for the HTTP and WebSocket surface."""

import asyncio
import json
import re

import pytest
from aiohttp.test_utils import TestClient, TestServer

from rvm.server.app import _opencv_distributions, create_app
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


async def test_connection_and_alarm_expose_live_regions(client):
    html = await (await client.get("/")).text()

    for element_id, role, live in (
        ("conn", "status", "polite"),
        ("alarm", "alert", "assertive"),
    ):
        match = re.search(rf'<[^>]+\bid="{element_id}"[^>]*>', html)
        assert match is not None, f"missing #{element_id}"
        assert f'role="{role}"' in match.group(0)
        assert f'aria-live="{live}"' in match.group(0)


async def test_stylesheet_is_served(client):
    response = await client.get("/static/style.css")

    assert response.status == 200
    assert "layout" in await response.text()


async def test_stylesheet_supports_focus_reduced_motion_and_mobile(client):
    css = await (await client.get("/static/style.css")).text()

    assert ":focus-visible" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert re.search(
        r"@media \(max-width: 900px\)[\s\S]*?grid-template-columns:\s*1fr",
        css,
    )
    assert "@media (max-width: 560px)" in css
    assert re.search(r"min-height:\s*40px", css)


async def test_operator_page_loads_no_remote_frontend_assets(client):
    html = await (await client.get("/")).text()
    css = await (await client.get("/static/style.css")).text()

    assert not re.search(r'(?:src|href)=["\'](?:https?:)?//', html)
    assert not re.search(r'url\(\s*["\']?(?:https?:)?//', css)
    assert not re.search(r'@import\s+["\'](?:https?:)?//', css)


async def test_client_script_is_served(client):
    response = await client.get("/static/app.js")

    assert response.status == 200
    assert "connect" in await response.text()


async def test_page_preserves_the_client_dom_contract(client):
    html = await (await client.get("/")).text()
    script = await (await client.get("/static/app.js")).text()

    referenced = set(re.findall(r'(?:\$|setText)\(\s*"([\w-]+)"', script))
    present = set(re.findall(r'\bid="([^"]+)"', html))

    assert referenced <= present, f"missing DOM ids: {sorted(referenced - present)}"


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

# --------------------------------------------------------------------------
# Optional analysis
# --------------------------------------------------------------------------


async def test_analysis_endpoints_report_an_empty_state(client):
    for path, field in (
        ("/api/tracks", "tracks"),
        ("/api/faces/identities", "identities"),
        ("/api/emotions", "emotions"),
        ("/api/gestures", "gestures"),
    ):
        response = await client.get(path)
        assert response.status == 200, path
        body = await response.json()
        assert body["count"] == 0, path
        assert body[field] == [], path


async def test_audio_events_endpoint_reports_the_capture_state(client):
    body = await (await client.get("/api/audio/events")).json()

    assert body == {"count": 0, "events": [], "running": False}


async def test_features_endpoint_lists_every_optional_analyser(client):
    body = await (await client.get("/api/features")).json()

    assert set(body) == {
        "enabled",
        "ready",
        "face_recognition",
        "emotion_recognition",
        "gesture_recognition",
        "audio_monitoring",
        "audio_available",
    }
    assert body["enabled"] is False
    assert body["ready"] is False
    assert body["face_recognition"] is False
    assert body["emotion_recognition"] is False
    assert body["gesture_recognition"] is False
    assert body["audio_monitoring"] is False
    # Nothing has probed the microphone yet in this fixture (no warm-up thread,
    # no audio-control request), so the answer is "not looked" rather than a
    # guess -- and, importantly, /api/status must not open PortAudio itself.
    assert body["audio_available"] is None


async def test_audio_control_rejects_a_truthy_string(client):
    response = await client.post("/api/audio/control", json={"enabled": "false"})

    assert response.status == 400


async def test_audio_control_needs_a_json_body(client):
    response = await client.post("/api/audio/control", data="not json")

    assert response.status == 400


async def test_audio_control_needs_the_enabled_key(client):
    response = await client.post("/api/audio/control", json={"on": True})

    assert response.status == 400


async def test_audio_control_reports_what_it_did(client):
    body = await (await client.post("/api/audio/control", json={"enabled": False})).json()

    assert body["requested"] is False
    assert body["running"] is False
    assert isinstance(body["available"], bool)



def test_the_opencv_warning_only_sees_opencv_distributions(monkeypatch):
    """The dual-install warning must not fire on unrelated packages."""
    from importlib.metadata import distributions

    class Dist:
        def __init__(self, name):
            self.metadata = {"Name": name}

    fake = [
        Dist("numpy"),
        Dist("opencv-python-headless"),
        Dist("OpenCV-Contrib-Python"),
        Dist("aiohttp"),
    ]
    monkeypatch.setattr("importlib.metadata.distributions", lambda: fake)

    assert _opencv_distributions() == [
        "opencv-contrib-python",
        "opencv-python-headless",
    ]


async def test_audio_control_makes_the_device_answer_available(client):
    body = await (await client.post("/api/audio/control", json={"enabled": False})).json()

    features = await (await client.get("/api/features")).json()
    assert isinstance(body["available"], bool)
    assert isinstance(features["audio_available"], bool)


# --------------------------------------------------------------------------
# Readability and structure
#
# The operator page was redone against docs/DESIGN-dashboard.md. The numbers
# below are that document's, not the stylesheet's: the type ladder, the two
# contrast floors and the group spacing are pinned here so a later edit to a
# single declaration fails at the commit that makes it, rather than at the
# projector on the day of the demonstration.
# --------------------------------------------------------------------------


def css_tokens(css: str) -> dict[str, str]:
    """The custom properties of the base ``:root`` block."""
    match = re.search(r":root\s*\{([^{}]*--bg[^{}]*)\}", css)
    assert match is not None, "the stylesheet has no base :root token block"
    return {
        name: value.strip()
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(1))
    }


def media_block(css: str, query: str) -> str:
    """The body of ``@media (<query>)``, found by matching its braces."""
    start = css.find("@media (" + query)
    assert start != -1, f"no @media ({query}) block"
    opening = css.index("{", start)
    depth = 0
    for index in range(opening, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[opening + 1 : index]
    raise AssertionError(f"unbalanced braces in the @media ({query}) block")


def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(colour: str) -> float:
    digits = colour.strip().lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", digits), colour
    red, green, blue = (int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    light, dark = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


def font_sizes(css: str) -> list[int]:
    sizes = [int(size) for size in re.findall(r"font-size:\s*(\d+)px", css)]
    sizes += [int(size) for size in re.findall(r"font:\s*[^;{}]*?\b(\d+)px/", css)]
    return sizes


async def test_the_type_ladder_is_13px_labels_and_15px_values(client):
    """AS-6: labels 13, values and body text 15, line height 1.5, nothing smaller.

    The old page ran 10px uppercase label micro-type with a 12px readout; both
    are gone, and a returning 10px is what this catches.
    """
    css = await (await client.get("/static/style.css")).text()
    tokens = css_tokens(css)

    assert tokens["--fs-label"] == "13px"
    assert tokens["--fs-body"] == "15px"

    body = re.search(r"\nbody\s*\{([^}]*)\}", css)
    assert body is not None, "no body rule"
    assert re.search(r"font:\s*var\(--fs-body\)/1\.5", body.group(1))

    labels = re.search(r"\.readouts dt\s*\{([^}]*)\}", css)
    values = re.search(r"\.readouts dd\s*\{([^}]*)\}", css)
    assert labels is not None, "the readout rows have no label rule"
    assert values is not None, "the readout rows have no value rule"
    assert "font-size: var(--fs-label)" in labels.group(1)
    assert re.search(r"font:\s*500\s+var\(--fs-body\)/1\.5", values.group(1))
    assert "tabular-nums" in values.group(1)

    sizes = font_sizes(css)
    assert sizes, "no font size is declared anywhere"
    assert min(sizes) >= 12, f"a font size below the 12px floor: {sorted(sizes)}"
    assert 15 in sizes
    assert css.count("var(--fs-label)") >= 8, "labels do not all use the label step"


async def test_mobile_keeps_body_text_at_15px_and_labels_at_14px(client):
    """AS-6: on the narrow side the labels step up, the values never step down."""
    css = await (await client.get("/static/style.css")).text()
    narrow = media_block(css, "max-width: 560px")

    assert "--fs-label: 14px" in narrow
    assert re.search(r"select,\s*button\s*\{[^}]*font-size:\s*15px", narrow)
    assert not re.search(r"font-size:\s*1[0-4]px", narrow)


async def test_the_grey_text_clears_7_7_to_1_and_body_text_clears_16_to_1(client):
    """AS-6: measured from the served palette, computed by WCAG 2.1.

    The expected numbers are DESIGN-dashboard.md §2's; recomputing them from the
    stylesheet hexes is what keeps the table and the page from drifting apart.
    """
    css = await (await client.get("/static/style.css")).text()
    tokens = css_tokens(css)
    background = tokens["--bg"]

    muted = contrast_ratio(tokens["--muted"], background)
    body = contrast_ratio(tokens["--text"], background)
    secondary = contrast_ratio(tokens["--text-2"], background)
    placeholder = contrast_ratio(tokens["--placeholder"], tokens["--panel"])

    assert round(muted, 2) == 7.73, f"grey text is {muted:.2f}:1 on {background}"
    assert round(body, 2) == 16.65, f"body text is {body:.2f}:1 on {background}"
    assert round(secondary, 2) == 11.94
    assert round(placeholder, 2) == 5.10

    assert muted >= 7.7
    assert body >= 16.0
    assert placeholder >= 5.0


async def test_groups_are_separated_by_at_least_20px_and_there_are_five_sections(client):
    """AS-7: whitespace separates groups, and there are five of them at most."""
    css = await (await client.get("/static/style.css")).text()
    html = await (await client.get("/")).text()

    wide = re.search(r"\.section\s*\+\s*\.section\s*\{([^}]*)\}", css)
    assert wide is not None, "the sections are not separated by a rule"
    margin = int(re.search(r"margin-top:\s*(\d+)px", wide.group(1)).group(1))
    padding = int(re.search(r"padding-top:\s*(\d+)px", wide.group(1)).group(1))
    assert margin >= 20
    assert margin + padding >= 20

    narrow = re.search(
        r"\.section\s*\+\s*\.section\s*\{([^}]*)\}",
        media_block(css, "max-width: 900px"),
    )
    assert narrow is not None, "the narrow layout has no section separation"
    narrow_margin = int(re.search(r"margin-top:\s*(\d+)px", narrow.group(1)).group(1))
    narrow_padding = int(re.search(r"padding-top:\s*(\d+)px", narrow.group(1)).group(1))
    assert narrow_margin + narrow_padding >= 20

    assert len(re.findall(r'class="section\b', html)) == 5
    assert len(re.findall(r"<h2", html)) == 5


async def test_the_redundant_frames_and_duplicate_labels_are_gone(client):
    """AS-7: one rule per readout and three boxes per control group is what made
    the first version unreadable. The only lines left are between sections."""
    css = await (await client.get("/static/style.css")).text()
    html = await (await client.get("/")).text()

    assert "border-bottom: 1px dashed" not in css
    assert "repeating-linear-gradient" not in css
    assert "linear-gradient" not in css

    # The channel label and the bottom overlay were a second copy of the two
    # OSD corners; the codec line was a readout row duplicating the section meta.
    assert "data-channel" not in html
    assert "<dt>Codec</dt>" not in html
    assert html.count('id="src-label"') == 1
    assert re.search(r'class="osd left" id="src-label"', html), (
        "the source label is not the picture's top-left OSD"
    )
    assert re.search(r'class="osd right" id="time-label"', html)

    heading = re.search(r"<h2[^>]*>Stream\s*(<span[^>]*id=\"m-codec\"[^>]*>[^<]*</span>)", html)
    assert heading is not None, "the codec is not the STREAM heading's meta"
    assert re.search(r'class="meta"[^>]*id="m-codec"', heading.group(1)) or re.search(
        r'id="m-codec"[^>]*class="meta"', heading.group(1)
    )


async def test_the_picture_is_the_first_focus_and_nothing_else_is_boxed(client):
    """AS-7: the largest area on the page is the picture, not the telemetry."""
    css = await (await client.get("/static/style.css")).text()
    html = await (await client.get("/")).text()

    stage = html.index('class="stage"')
    controls = html.index('class="controls"')
    rail = html.index('class="rail"')
    assert stage < controls < rail

    stage_rule = re.search(r"\.stage\s*\{([^}]*)\}", css)
    assert stage_rule is not None
    assert re.search(r"aspect-ratio:\s*4\s*/\s*3", stage_rule.group(1))

    for selector in (r"\.rail\s*\{", r"\.section\s*\{"):
        rule = re.search(selector + r"([^}]*)\}", css)
        assert rule is not None, selector
        assert "background" not in rule.group(1), f"{selector} paints a box"


async def test_the_peak_rule_and_its_tag_share_the_traces_maximum(client):
    """AS-6/AS-7: the trace is scaled to its own window maximum and the tag
    prints that same number, so the shape always has a magnitude to check."""
    css = await (await client.get("/static/style.css")).text()
    html = await (await client.get("/")).text()
    script = await (await client.get("/static/app.js")).text()

    peak_tag = re.search(r'id="m-peak"[^>]*>([^<]+)<', html)
    assert peak_tag is not None, "no peak tag"
    assert peak_tag.group(1).startswith("peak")

    stream = html.index(">Stream")
    transport = html.index(">Transport")
    assert stream < html.index('id="m-peak"') < transport, "the tag left the STREAM section"

    canvas = re.search(r"<canvas[^>]*id=\"spark\"[^>]*>", html)
    assert canvas is not None
    assert 'role="img"' in canvas.group(0)
    assert 'aria-label="' in canvas.group(0)

    rule = re.search(r"\.peak\s*\{([^}]*)\}", css)
    assert rule is not None, "the peak tag has no rule"
    assert re.search(r"font:\s*400\s+12px/1\.5\s+var\(--mono\)", rule.group(1))
    assert "color: var(--muted)" in rule.group(1)
    assert "margin-left: auto" in rule.group(1)

    # One maximum, used twice: for the scale and for the tag.
    assert re.search(r"const peak = Math\.max\(\.\.\.history\.bitrate\)", script), (
        "the peak is not the history maximum"
    )
    assert "(v / peak)" in script, "the trace is not normalised to that peak"
    assert re.search(r'setText\(\s*"m-peak",\s*fmtPeak\(peak\)\s*\)', script)
    assert "setLineDash([3" in script
    assert "rgba(154,165,170,.5)" in script


async def test_narrow_layout_orders_picture_controls_registry_then_telemetry(client):
    """AS-7/AS-5: at 390 the order is the one a thumb expects, and it is done by
    reordering boxes rather than by moving markup."""
    css = await (await client.get("/static/style.css")).text()
    narrow = media_block(css, "max-width: 900px")

    assert re.search(r"\.viewer,\s*\.rail\s*\{[^}]*display:\s*contents", narrow)
    for selector, order in (
        (r"\.stage", 1),
        (r"\.controls", 2),
        (r"\.registry", 4),
        (r"\.section", 5),
    ):
        rule = re.search(selector + r"\s*\{([^}]*)\}", narrow)
        assert rule is not None, selector
        assert re.search(rf"order:\s*{order}\b", rule.group(1)), selector

    assert re.search(r"grid-template-columns:\s*1fr", narrow)


async def test_the_page_keeps_every_id_and_all_eight_operations(client):
    """AS-5: the redesign may move things, never remove them."""
    html = await (await client.get("/")).text()
    script = await (await client.get("/static/app.js")).text()

    kept = (
        "stream view-source view-decoded roi bbox tracks stage alarm conn conn-text "
        "src-label time-label view-label bitrate apply sensitivity clear-roi snapshot "
        "record metrics clips spark m-res m-fps m-qp m-psnr m-bitrate m-codec m-pkts "
        "m-pics m-loss m-jitter m-clients m-rec m-motion m-faces m-tracks m-gestures "
        "m-emotions m-audio m-roi m-identities m-peak zone-help face-name face-remember "
        "face-status face-list"
    ).split()
    missing = [element_id for element_id in kept if f'id="{element_id}"' not in html]
    assert not missing, f"missing DOM ids: {missing}"

    # Seven controls on the page plus dragging the zone out on the picture.
    for control in (
        "apply",
        "clear-roi",
        "view-source",
        "view-decoded",
        "snapshot",
        "record",
        "metrics",
    ):
        assert f'$("{control}")' in script, control
    assert script.count(".onclick = ") >= 7
    assert re.search(r'\$\("sensitivity"\)\.onchange', script)
    assert 'stage.addEventListener("pointerdown"' in script
    assert 'stage.addEventListener("pointerup"' in script
    assert 'postJSON("/api/motion"' in script


async def test_the_registry_section_holds_the_name_input_and_the_list(client):
    """AS-1 seam: the block the registry ticket will wire is already a section of
    its own, so the narrow-screen order it must appear in can be checked here."""
    html = await (await client.get("/")).text()

    assert 'class="section registry" id="face-registry"' in html
    assert re.search(r'<h2[^>]*>Face registry</h2>', html)
    assert 'for="face-name"' in html
    assert 'id="face-name"' in html
    assert 'id="face-remember"' in html and ">REMEMBER FACE</button>" in html
    assert 'id="face-status"' in html
    assert 'id="face-list"' in html

    sections = re.findall(r'class="section\b[^"]*"', html)
    assert len(sections) == 5
    assert "registry" in sections[3], "the registry is not the fourth section"
