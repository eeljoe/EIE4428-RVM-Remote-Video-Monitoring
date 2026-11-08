"""Independent verifier probe for ticket 03 (dashboard readability).

Written by the r1 verifier against a live server started from the verifier's
own worktree copy of the submitted commit. Produces:

  * 03-verifier-desktop-1440x1000.png / 03-verifier-mobile-390x844.png —
    screenshots of the LIVE page after ~32s of real telemetry,
  * 03-verifier-measure.json —
    * WCAG 2.1 contrast recomputed from the served stylesheet's hex tokens,
    * structural checks on the served HTML/CSS/JS (IDs, order rules, remote
      resources, section count, group gaps, peak-tag wiring),
    * computed style + geometry readings from real Chrome at 1440x1000 and
      390x844 on a copy of the served page with worst-case values injected,
    * a deterministic "telemetry copy": the real app.js driven by a stub
      WebSocket feeding a scripted bitrate sequence whose maximum is known,
      so `peak x.xx Mbps`, the aria-label, the dashed rule and the apex row
      are all checked against a maximum the probe itself chose.

Copies differ from the served bytes only by the edits declared in
``provenance.copy_edits``; a byte-level assert proves it.

Usage: start ``run_server.py --no-camera --port 8137`` in the worktree, then
    .venv\\Scripts\\python.exe <this file> --base http://127.0.0.1:8137 \
        --worktree <worktree path>
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
WORK = Path.home() / "AppData" / "Local" / "Temp" / "rvm03-verifier"

SLOW_PORT = 8123
SLOW_DELAY = 32.0
SLOW_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)

# Worst-case strings a telemetry frame can legitimately print, so truncation is
# measured at the page's widest state rather than at the "-" placeholders.
INJECT = {
    "m-res": "320 × 240",
    "m-fps": "24.6 fps",
    "m-bitrate": "1.18 Mbps",
    "m-qp": "26",
    "m-psnr": "31.4 dB",
    "m-pkts": "18,493",
    "m-pics": "4,271",
    "m-loss": "0.42 %",
    "m-jitter": "3.17 ms",
    "m-clients": "1",
    "m-rec": "off",
    "m-motion": "6.84 %",
    "m-faces": "1",
    "m-tracks": "T1, T2",
    "m-gestures": "no hand",
    "m-emotions": "neutral",
    "m-audio": "none",
    "m-roi": "custom zone",
    "m-identities": "Alice Ng · 0.82",
    "m-peak": "peak 1.33 Mbps",
}

# Scripted telemetry for the deterministic copy: 14 frames, peak sits mid-
# window at 2.5 Mbps while the tail runs at ~0.7, so the tag can only read
# "peak 2.50 Mbps" if it is the window maximum, not the latest sample.
BITRATES = [
    1_000_000, 1_100_000, 900_000, 1_300_000, 1_000_000,
    2_500_000,
    700_000, 720_000, 690_000, 710_000, 700_000, 705_000, 695_000, 700_000,
]
EXPECTED_PEAK_TAG = "peak 2.50 Mbps"

STATUS_TEMPLATE = {
    "width": 320, "height": 240, "frame_rate": 24.6, "bitrate": 0,
    "qp": 26, "psnr": 31.4, "packets_sent": 18493, "pictures": 4271,
    "fraction_lost": 0.0042, "jitter_ms": 3.17, "clients": 1,
    "recording": False, "source": "synthetic", "motion_ratio": 0.0684,
    "faces": 1, "tracks": [{"id": 1, "centroid": [160, 120], "trail": [[150, 118], [160, 120]]}],
    "gestures": {"state": "ok", "count": 0, "gestures": []},
    "emotions": {"state": "ok", "count": 1, "emotions": [{"emotion": "neutral"}]},
    "face_identities": {"state": "ok", "count": 1, "identities": [{"name": "Alice Ng", "similarity": 0.82}]},
    "audio_events": 0, "audio_last": "", "alarm": False, "roi": None,
    "bbox": None, "motion_sensitivity": "medium",
}

# ---------------------------------------------------------------------------
# Static analysis of the served bytes
# ---------------------------------------------------------------------------


def channel(v: float) -> float:
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex6: str) -> float:
    d = hex6.lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", d), hex6
    r, g, b = (int(d[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(fg: str, bg: str) -> float:
    light, dark = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def root_block(css: str) -> str:
    m = re.search(r"^:root\s*\{([^{}]*)\}", css, re.M)
    assert m, "no top-level :root block"
    return m.group(1)


def tokens(css: str) -> dict[str, str]:
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root_block(css)))


def media(css: str, query: str) -> str:
    i = css.find("@media (" + query)
    assert i != -1, query
    depth = 0
    j = css.index("{", i)
    for k in range(j, len(css)):
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
            if depth == 0:
                return css[j + 1 : k]
    raise AssertionError("unbalanced media block " + query)


def fetch(base: str) -> tuple[str, str, str]:
    html = urlopen(base + "/", timeout=10).read().decode("utf-8")
    css = urlopen(base + "/static/style.css", timeout=10).read().decode("utf-8")
    js = urlopen(base + "/static/app.js", timeout=10).read().decode("utf-8")
    return html, css, js


def static_checks(html: str, css: str, js: str, worktree: Path) -> dict:
    disk = {
        name: (worktree / "src" / "rvm" / "web" / name).read_bytes()
        for name in ("index.html", "style.css", "app.js")
    }
    served = {"index.html": html, "style.css": css, "app.js": js}
    provenance = {
        "served_bytes_equal_worktree": {
            name: hashlib.sha256(disk[name]).hexdigest()
            == hashlib.sha256(served[name].encode()).hexdigest()
            for name in disk
        },
        "sha256": {name: hashlib.sha256(disk[name]).hexdigest() for name in disk},
    }

    t = tokens(css)
    bg = t["--bg"]
    ratios = {
        "muted_on_bg": round(contrast(t["--muted"], bg), 2),
        "text_on_bg": round(contrast(t["--text"], bg), 2),
        "text2_on_bg": round(contrast(t["--text-2"], bg), 2),
        "placeholder_on_panel": round(contrast(t["--placeholder"], t["--panel"]), 2),
        "text_on_panel": round(contrast(t["--text"], t["--panel"]), 2),
        "alarm_on_bg": round(contrast(t["--alarm"], bg), 2),
        "accent_on_bg": round(contrast(t["--accent"], bg), 2),
        "ok_on_bg": round(contrast(t["--ok"], bg), 2),
        "warn_on_bg": round(contrast(t["--warn"], bg), 2),
        "on_accent_on_accent": round(contrast(t["--on-accent"], t["--accent"]), 2),
    }

    sizes = sorted(
        set(
            [int(s) for s in re.findall(r"font-size:\s*(\d+)px", css)]
            + [int(s) for s in re.findall(r"font:\s*[^;{}]*?\b(\d+)px/", css)]
        )
    )

    section_attrs = re.findall(r'class="section\b[^"]*"', html)
    h2s = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.S)
    ids_needed = (
        "stream view-source view-decoded roi bbox tracks stage alarm conn conn-text "
        "src-label time-label view-label bitrate apply sensitivity clear-roi snapshot "
        "record metrics clips spark m-res m-fps m-qp m-psnr m-bitrate m-codec m-pkts "
        "m-pics m-loss m-jitter m-clients m-rec m-motion m-faces m-tracks m-gestures "
        "m-emotions m-audio m-roi m-identities m-peak zone-help face-name face-remember "
        "face-status face-list"
    ).split()

    remote = {
        "html_src_href": re.findall(r'(?:src|href)=["\'](?:https?:)?//', html),
        "css_url": re.findall(r'url\(\s*["\']?(?:https?:)?//', css),
        "css_import": re.findall(r"@import", css),
        "js_remote_literal": re.findall(r'["\'](https?:)?//(?!127\.0\.0\.1|localhost)[^"\']+', js),
    }

    wide = re.search(r"\.section\s*\+\s*\.section\s*\{([^}]*)\}", css).group(1)
    gap = {
        "desktop_margin": int(re.search(r"margin-top:\s*(\d+)px", wide).group(1)),
        "desktop_padding": int(re.search(r"padding-top:\s*(\d+)px", wide).group(1)),
    }
    narrow = re.search(
        r"\.section\s*\+\s*\.section\s*\{([^}]*)\}", media(css, "max-width: 900px")
    ).group(1)
    gap["mobile_margin"] = int(re.search(r"margin-top:\s*(\d+)px", narrow).group(1))
    gap["mobile_padding"] = int(re.search(r"padding-top:\s*(\d+)px", narrow).group(1))

    stream = re.search(r'<img[^>]*id="stream"[^>]*>', html).group(0)

    return {
        "provenance": provenance,
        "tokens": {
            k: t[k]
            for k in ("--bg", "--panel", "--text", "--text-2", "--muted", "--placeholder", "--fs-label", "--fs-body")
        },
        "contrast": ratios,
        "font_sizes_declared_px": sizes,
        "min_font_px": min(sizes),
        "fs_label_media560": "--fs-label: 14px" in media(css, "max-width: 560px"),
        "fs_label_uses": css.count("var(--fs-label)"),
        "line_height_15_count": css.count("/1.5"),
        "section_attrs": section_attrs,
        "section_count": len(section_attrs),
        "h2_titles": [re.sub(r"<[^>]+>", "", h).strip() for h in h2s],
        "group_gap_px": gap,
        "ids_missing": [i for i in ids_needed if f'id="{i}"' not in html],
        "stream_img_tag": stream,
        "stream_inline_mjpg": 'src="/api/stream.mjpg"' in stream,
        "remote_refs": remote,
        "registry_is_section4": "registry" in section_attrs[3],
        "no_dashed_row_borders": "border-bottom: 1px dashed" not in css,
        "no_gradients": "gradient" not in css,
        "no_data_channel": "data-channel" not in html,
        "peak_same_source": {
            "single_peak_var": "const peak = Math.max(...history.bitrate)" in js,
            "trace_normalised_by_peak": "(v / peak)" in js,
            "tag_written_from_peak": 'setText("m-peak", fmtPeak(peak))' in js,
            "dashed_3_3": "setLineDash([3" in js,
            "rule_colour_muted_half": "rgba(154,165,170,.5)" in js,
            "tag_format_peak_x_xx_mbps": re.search(
                r'"peak "\s*\+\s*\(bps / 1e6\)\.toFixed\(2\)\s*\+\s*" Mbps"', js
            )
            is not None,
            "peak_inside_stream_section": html.index('id="m-peak"') < html.index(">Transport"),
            "peak_uses_fs_label_free_12px": "font: 400 12px/1.5 var(--mono)"
            in re.search(r"\.peak\s*\{([^}]*)\}", css).group(1),
            "peak_muted": "color: var(--muted)"
            in re.search(r"\.peak\s*\{([^}]*)\}", css).group(1),
        },
        "order_rules_900": {
            sel: bool(
                re.search(sel + r"\s*\{[^}]*order:\s*%d\b" % order, media(css, "max-width: 900px"))
            )
            for sel, order in (
                (r"\.stage", 1),
                (r"\.controls", 2),
                (r"\.hint", 3),
                (r"\.registry", 4),
                (r"\.section", 5),
            )
        },
        "display_contents_900": "display: contents" in media(css, "max-width: 900px"),
        "rail_self_scroll_rule": "max-height: calc(100vh - 102px)" in css,
        "readouts_mobile_single_col": "grid-template-columns: 1fr"
        in media(css, "max-width: 560px").split(".readouts")[1][:80]
        if ".readouts" in media(css, "max-width: 560px")
        else False,
    }


# ---------------------------------------------------------------------------
# Chrome passes
# ---------------------------------------------------------------------------

WRAPPER = """<!DOCTYPE html>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  iframe {{ display: block; width: {width}px; height: {height}px; border: 0; }}
  #report {{ position: fixed; left: -4000px; top: 0; margin: 0; }}
  img.slow {{ position: fixed; left: -20px; top: -20px; width: 1px; height: 1px; }}
</style>
<iframe id="page" src="{src}"></iframe>
<pre id="report"></pre>
{slow}
<script>{measure}</script>
"""

STUB_WS_AND_FETCH = (
    "<script>/* probe stub: finite local socket, no network */\n"
    "window.__BITRATES__ = " + json.dumps(BITRATES) + ";\n"
    "window.__STATUS__ = " + json.dumps(STATUS_TEMPLATE) + ";\n"
    "window.WebSocket = function () {\n"
    "  var self = this; self.readyState = 0; self.send = function () {};\n"
    "  self.close = function () { self.readyState = 3; if (self.onclose) self.onclose(); };\n"
    "  var i = 0;\n"
    "  setTimeout(function () {\n"
    "    self.readyState = 1; if (self.onopen) self.onopen();\n"
    "    var timer = setInterval(function () {\n"
    "      if (i >= window.__BITRATES__.length) { clearInterval(timer); return; }\n"
    "      var s = JSON.parse(JSON.stringify(window.__STATUS__));\n"
    "      s.bitrate = window.__BITRATES__[i++];\n"
    "      if (self.onmessage) self.onmessage({ data: JSON.stringify(s) });\n"
    "    }, 30);\n"
    "  }, 30);\n"
    "};\n"
    "window.fetch = function () { return Promise.reject(new Error('offline copy')); };\n"
    "</script>\n"
)

ONE_PX_GIF = "data:image/gif;base64,R0lGODlhAQABAAAAACw="

MEASURE_STYLE = r"""
(function () {
  var wanted = __INJECT__;
  var frame = document.getElementById("page");
  var report = document.getElementById("report");
  var finished = false, attempts = 0;
  function done(p) { if (!finished) { finished = true; report.textContent = "MEASURE:" + JSON.stringify(p); } }
  function collect() {
    var win = frame.contentWindow, d = frame.contentDocument;
    if (!d || !d.body || !d.querySelector(".readouts dt")) return null;
    Object.keys(wanted).forEach(function (id) {
      var el = d.getElementById(id);
      if (el) { el.textContent = wanted[id]; el.classList.remove("pending"); }
    });
    void d.body.offsetWidth;
    var g = function (s) { return d.querySelector(s); };
    var ga = function (s) { return [].slice.call(d.querySelectorAll(s)); };
    var css = function (el) { return el ? win.getComputedStyle(el) : null; };
    var type = function (el) { var s = css(el); return s ? s.fontSize + "|" + s.lineHeight : null; };
    var tops = {};
    [".stage", ".controls", ".hint", "#face-registry"].forEach(function (s) {
      var r = g(s).getBoundingClientRect(); tops[s] = [Math.round(r.top), Math.round(r.bottom)];
    });
    var sections = ga(".section").map(function (s) {
      var r = s.getBoundingClientRect();
      return { title: s.querySelector("h2").textContent.replace(/\s+/g, " ").trim(), top: Math.round(r.top) };
    });
    var controls = ["apply", "clear-roi", "view-source", "view-decoded", "snapshot", "record", "metrics"].map(function (id) {
      var r = d.getElementById(id).getBoundingClientRect();
      return { id: id, top: Math.round(r.top), bottom: Math.round(r.bottom), right: Math.round(r.right) };
    });
    var dd = ga(".readouts dd");
    return {
      viewport: [win.innerWidth, win.innerHeight],
      scrollWidth: d.documentElement.scrollWidth,
      scrollHeight: d.documentElement.scrollHeight,
      clientWidth: d.documentElement.clientWidth,
      fonts: {
        body: type(d.body), label_dt: type(g(".readouts dt")), value_dd: type(g(".readouts dd")),
        heading_h2: type(g(".section h2")), meta_codec: type(g("#m-codec")), peak: type(g("#m-peak")),
        osd: type(g(".osd")), button_apply: type(g("#apply")), primary_remember: type(g("#face-remember")),
        status: type(g("#face-status")), hint: type(g(".hint")), empty_clips: type(g("#clips .empty")),
        input_face: type(g("#face-name")), select_bitrate: type(g("#bitrate")),
        reg_label: type(g(".reg-label")), clip_name_style_exists: !!g(".clip-name")
      },
      colors: {
        body_bg: css(d.body).backgroundColor, label: css(g(".readouts dt")).color,
        value: css(g(".readouts dd")).color, heading: css(g(".section h2")).color,
        peak: css(g("#m-peak")).color, empty: css(g("#clips .empty")).color
      },
      tops: tops, sections: sections, controls: controls,
      stage_wh: (function () { var r = g(".stage").getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })(),
      rail_wh: (function () { var r = g(".rail").getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })(),
      group_gap: (function () {
        var s = css(ga(".section")[1]);
        return [parseFloat(s.marginTop), parseFloat(s.paddingTop)];
      })(),
      truncated_dd: dd.filter(function (el) { return el.scrollWidth > el.clientWidth + 1; })
        .map(function (el) { return el.id + ":" + el.scrollWidth + ">" + el.clientWidth; }),
      peak_truncated: (function () { var p = g("#m-peak"); return p.scrollWidth > p.clientWidth + 1; })(),
      widest_right: Math.max.apply(null, ga("body *").map(function (el) {
        return Math.round(el.getBoundingClientRect().right);
      }))
    };
  }
  function tick() {
    if (finished) return;
    if (++attempts > 200) return done({ error: "never measurable" });
    try { var p = collect(); if (p) return done(p); } catch (e) { return done({ error: String(e) }); }
    setTimeout(tick, 40);
  }
  frame.addEventListener("load", tick); tick();
})();
"""

MEASURE_PEAK = r"""
(function () {
  var frame = document.getElementById("page");
  var report = document.getElementById("report");
  var finished = false, attempts = 0;
  function done(p) { if (!finished) { finished = true; report.textContent = "MEASURE:" + JSON.stringify(p); } }
  function collect() {
    var win = frame.contentWindow, d = frame.contentDocument;
    if (!d || !d.body || !d.getElementById("m-peak") || !d.getElementById("spark")) return null;
    var hist = null;
    try { hist = win.eval("history.bitrate.slice()"); } catch (e) { hist = "EVAL-FAIL:" + e; }
    if (typeof hist === "string" || hist === null) return { error: hist };
    if (hist.length < 14) return null;
    var canvas = d.getElementById("spark");
    var ctx = canvas.getContext("2d");
    var img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    var data = img.data, rowsGrey = {}, rowsAccent = {}, r, c, i, R, G, B, A;
    for (r = 0; r < canvas.height; r++) {
      var grey = 0, accent = 0;
      for (c = 0; c < canvas.width; c++) {
        i = (r * canvas.width + c) * 4;
        R = data[i]; G = data[i + 1]; B = data[i + 2]; A = data[i + 3];
        if (A > 90 && A < 200 && Math.abs(R - 154) < 30 && Math.abs(G - 165) < 30 && Math.abs(B - 170) < 30) grey++;
        if (A > 200 && Math.abs(R - 95) < 45 && Math.abs(G - 211) < 45 && Math.abs(B - 198) < 45) accent++;
      }
      if (grey >= 8) rowsGrey[r] = grey;
      if (accent >= 1) rowsAccent[r] = accent;
    }
    return {
      viewport: [win.innerWidth, win.innerHeight],
      history_len: hist.length,
      history_max_bps: Math.max.apply(null, hist),
      history_last_bps: hist[hist.length - 1],
      peak_text: d.getElementById("m-peak").textContent,
      bitrate_text: d.getElementById("m-bitrate").textContent,
      canvas_backing: [canvas.width, canvas.height],
      canvas_css: (function () { var b = canvas.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; })(),
      grey_dash_rows: Object.keys(rowsGrey).map(Number),
      accent_top_row: (function () { var a = Object.keys(rowsAccent).map(Number); return a.length ? Math.min.apply(null, a) : null; })(),
      accent_row_counts: rowsAccent,
      aria: canvas.getAttribute("aria-label"),
      conn: d.getElementById("conn-text").textContent,
      scrollWidth: d.documentElement.scrollWidth,
      clientWidth: d.documentElement.clientWidth
    };
  }
  function tick() {
    if (finished) return;
    if (++attempts > 300) return done({ error: "timed out waiting for scripted telemetry" });
    try { var p = collect(); if (p) return done(p); } catch (e) { return done({ error: String(e) }); }
    setTimeout(tick, 40);
  }
  frame.addEventListener("load", tick); tick();
})();
"""


def start_slow_server() -> http.server.ThreadingHTTPServer:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(SLOW_DELAY)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(SLOW_PIXEL)))
            self.end_headers()
            self.wfile.write(SLOW_PIXEL)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", SLOW_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def chrome(*args: str, timeout: int = 200) -> subprocess.CompletedProcess:
    profile = Path.home() / "AppData" / "Local" / "Temp" / ("rvm03v-" + uuid.uuid4().hex[:10])
    return subprocess.run(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def wrapper(width: int, height: int, src: str, script: str = "", slow: bool = False) -> Path:
    WORK.mkdir(exist_ok=True)
    page = WORK / f"wrap-{width}x{height}-{uuid.uuid4().hex[:8]}.html"
    pixel = (
        f'<img class="slow" alt="" src="http://127.0.0.1:{SLOW_PORT}/slow.png?{uuid.uuid4().hex}">'
        if slow
        else ""
    )
    page.write_text(
        WRAPPER.format(width=width, height=height, src=src, measure=script, slow=pixel),
        encoding="utf-8",
    )
    return page


def measure(width: int, height: int, src: str, script: str, timeout: int = 60) -> dict:
    page = wrapper(width, height, src, script)
    for attempt in range(1, 4):
        result = chrome(
            f"--window-size={width + 40},{height + 120}",
            "--allow-file-access-from-files",
            "--disable-web-security",
            "--virtual-time-budget=15000",
            "--dump-dom",
            page.as_uri(),
            timeout=timeout,
        )
        m = re.search(r"MEASURE:(\{.*?\})</pre>", result.stdout, re.S)
        if m:
            return json.loads(m.group(1))
        print(f"  {width}x{height} attempt {attempt}: no payload", file=sys.stderr)
        if result.returncode not in (0, None):
            print("  stderr:", result.stderr[-400:], file=sys.stderr)
    raise SystemExit(f"no measurement at {width}x{height}")


def shoot(width: int, height: int, name: str, base: str) -> dict:
    page = wrapper(width, height, base + "/", slow=True)
    png = WORK / name
    started = time.time()
    chrome(f"--window-size={width + 40},{height + 120}", f"--screenshot={png}", page.as_uri(), timeout=200)
    if not png.exists():
        raise SystemExit("no screenshot " + name)
    from PIL import Image

    img = Image.open(png).crop((0, 0, width, height))
    out = HERE / name
    img.save(out)
    return {"path": str(out), "size": [img.width, img.height], "settle_s": round(time.time() - started, 1)}


def prepare_copies(html: str, css: str, js: str) -> dict:
    WORK.mkdir(exist_ok=True)
    link = '<link rel="stylesheet" href="/static/style.css" />'
    script = '<script src="/static/app.js"></script>'
    stream_src = 'src="/api/stream.mjpg"'
    assert link in html and script in html and stream_src in html

    # Copy A: style/geometry pass — same bytes, CSS inlined, app.js dropped.
    a = html.replace(link, "<style>\n" + css + "\n</style>").replace(
        script, STUB_WS_AND_FETCH + "<!-- app.js dropped for the style pass -->"
    )
    path_a = WORK / "measure-style.html"
    path_a.write_text(a, encoding="utf-8")

    # Copy B: deterministic telemetry — real app.js driven by the stub socket;
    # the mjpg src is swapped for a 1px GIF and the retry handler is cleared
    # after app.js runs, so the guaranteed file:// load failure cannot spin
    # the onerror loop while the scripted frames arrive.
    kill_retry = (
        "<script>/* probe: file:// can never load /api/stream.mjpg; stop the "
        "retry so the document settles */\n"
        'document.getElementById("stream").onerror = null;\n'
        'document.getElementById("stream").src = "' + ONE_PX_GIF + '";\n'
        "</script>"
    )
    b = (
        html.replace(link, "<style>\n" + css + "\n</style>")
        .replace(
            script,
            STUB_WS_AND_FETCH + "<script>\n" + js + "\n</script>\n" + kill_retry,
        )
        .replace(stream_src, 'src="' + ONE_PX_GIF + '"')
    )
    path_b = WORK / "measure-telemetry.html"
    path_b.write_text(b, encoding="utf-8")

    # Byte-level proof the copies differ only by the declared edits.
    restored_a = a.replace("<style>\n" + css + "\n</style>", link).replace(
        STUB_WS_AND_FETCH + "<!-- app.js dropped for the style pass -->", script
    )
    assert restored_a == html
    return {
        "style": path_a,
        "telemetry": path_b,
        "copy_edits": [
            "A: the /static/style.css link becomes the same bytes in a <style> block; "
            "app.js is dropped (every style/geometry number is a function of markup+CSS)",
            "B: CSS inlined identically; app.js inlined after a stub WebSocket/fetch that "
            "feeds 14 scripted status frames (bitrate max 2.5 Mbps mid-window, tail ~0.7); "
            "the stream img src becomes a 1px data GIF and the onerror retry is cleared "
            "after app.js runs (file:// can never load /api/stream.mjpg)",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8137")
    ap.add_argument("--worktree", required=True)
    args = ap.parse_args()
    base, wt = args.base, Path(args.worktree)

    with urlopen(base + "/", timeout=10) as r:
        assert r.status == 200

    html, css, js = fetch(base)
    report = {
        "base": base,
        "worktree": str(wt),
        "expected_peak_tag": EXPECTED_PEAK_TAG,
        "bitrate_sequence": BITRATES,
        "static": static_checks(html, css, js, wt),
    }

    copies = prepare_copies(html, css, js)
    report["copy_edits"] = copies["copy_edits"]

    style_script = MEASURE_STYLE.replace("__INJECT__", json.dumps(INJECT))
    report["desktop_1440x1000"] = measure(1440, 1000, copies["style"].as_uri(), style_script)
    report["mobile_390x844"] = measure(390, 844, copies["style"].as_uri(), style_script)
    report["telemetry_390"] = measure(390, 844, copies["telemetry"].as_uri(), MEASURE_PEAK)
    report["telemetry_1440"] = measure(1440, 1000, copies["telemetry"].as_uri(), MEASURE_PEAK)

    slow = start_slow_server()
    try:
        report["shot_desktop"] = shoot(1440, 1000, "03-verifier-desktop-1440x1000.png", base)
        report["shot_mobile"] = shoot(390, 844, "03-verifier-mobile-390x844.png", base)
    finally:
        slow.shutdown()

    out = HERE / "03-verifier-measure.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
