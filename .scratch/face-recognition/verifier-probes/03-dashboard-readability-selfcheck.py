"""Real-browser self-check for ticket 03 (whole-page readability rebuild).

Runs against the live server -- the page the operator gets, not a copy of it --
at the two sign-off viewports, and produces

  * a 1440x1000 and a 390x844 screenshot, cropped to the viewport, and
  * a measurement pass that reads computed styles and geometry back out of the
    rendered document, so the ticket's numbers are readings and not claims.

Two tricks are needed, both borrowed from the reference-mock capture in
``design/v2/_build``:

  * the page is framed in an iframe of exactly the target size, because Chrome
    sizes the *window* and what that does to the layout viewport depends on the
    window frame and on whether a scrollbar is showing;
  * the measuring page is a local file, so it needs ``--disable-web-security``
    to read the framed document's computed styles.

The screenshot is taken of the *live* page. The measuring pass is taken of a
copy of what the server serves, because the live page holds a never-ending
multipart response open: Chrome's ``--dump-dom`` fires about 1.7s after the
navigation, before the framed page has even parsed, and no flag makes it wait.
The copy is the served HTML with exactly two strings rewritten -- the two
``/static/...`` URLs become relative ones so a file on disk can find them -- and
the probe asserts that modulo those two rewrites the copy is byte-identical to
``GET /``. Nothing else about the page changes; every number below is read out
of the same stylesheet the operator gets.

The readouts are filled with the reference values from DESIGN-dashboard.md §10
before anything is measured, so the widest rows the page can ever show are the
ones measured -- a measured row of grey hyphens would prove nothing about
overflow.

Start the server first::

    .venv\\Scripts\\python.exe run_server.py --no-camera --port 8099
    .venv\\Scripts\\python.exe .scratch\\face-recognition\\verifier-probes\\03-dashboard-readability-selfcheck.py
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8099"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
VIEWPORTS = (
    (1440, 1000, "03-desktop-1440x1000.png"),
    (390, 844, "03-mobile-390x844.png"),
)

# The sample strings from DESIGN-dashboard.md §10, i.e. the widest values the
# page ever prints. The measurement injects them so a row is measured at its
# worst case instead of at the grey hyphen it shows before telemetry arrives.
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
    "m-tracks": "T1",
    "m-gestures": "no hand",
    "m-emotions": "neutral",
    "m-audio": "none",
    "m-roi": "custom zone",
    "m-identities": "Alice Ng · 0.82",
    "m-peak": "peak 1.33 Mbps",
}

STUB = (
    "<script>/* offline measurement copy: no socket and no telemetry fetch, so the\n"
    "   document settles the way a page without a live stream does */\n"
    "window.WebSocket = function () { this.readyState = 3; this.send = function () {};"
    " this.close = function () {}; };\n"
    "window.fetch = function () { return Promise.reject(new Error('offline copy')); };\n"
    "</script>\n"
)

MEASURE = r"""
(function () {
  var wanted = __INJECT__;
  var override = __OVERRIDE__;
  var frame = document.getElementById("page");
  var report = document.getElementById("report");
  var finished = false;
  var attempts = 0;

  function done(payload) {
    if (finished) return;
    finished = true;
    report.textContent = "MEASURE:" + JSON.stringify(payload);
  }

  function collect() {
    var win = frame.contentWindow;
    var d = frame.contentDocument;
    if (!d || !d.body || !d.querySelector(".readouts dt") || !d.getElementById("m-peak")) {
      return null;
    }
    Object.keys(wanted).forEach(function (id) {
      var el = d.getElementById(id);
      if (el) {
        el.textContent = wanted[id];
        el.classList.remove("pending");
      }
    });
    if (override) {
      var style = d.createElement("style");
      style.textContent = override;
      d.head.appendChild(style);
    }
    void d.body.offsetWidth;

    var g = function (selector) { return d.querySelector(selector); };
    var css = function (el) { return el ? win.getComputedStyle(el) : null; };
    var type = function (el) {
      var s = css(el);
      return s ? s.fontSize + " / " + s.lineHeight : null;
    };
    var dd = [].slice.call(d.querySelectorAll(".readouts dd"));
    var elements = [].slice.call(d.querySelectorAll("body *"));

    return {
      viewport: [win.innerWidth, win.innerHeight],
      scroll: {
        width: d.documentElement.scrollWidth,
        height: d.documentElement.scrollHeight,
        client: d.documentElement.clientWidth
      },
      background: css(d.body).backgroundColor,
      fonts: {
        body: type(d.body),
        label: type(g(".readouts dt")),
        value: type(g(".readouts dd")),
        heading: type(g(".section h2")),
        meta: type(g("#m-codec")),
        peak: type(g("#m-peak")),
        osd: type(g(".osd")),
        select: type(g("#bitrate")),
        button: type(g("#apply")),
        primary: type(g("#face-remember")),
        status: type(g("#face-status")),
        hint: type(g(".hint")),
        empty: type(g("#clips .empty")),
        clip: type(g(".clips .clip-sub"))
      },
      colors: {
        label: css(g(".readouts dt")).color,
        value: css(g(".readouts dd")).color,
        heading: css(g(".section h2")).color,
        peak: css(g("#m-peak")).color,
        body: css(d.body).color
      },
      sections: [].slice.call(d.querySelectorAll(".section")).map(function (section) {
        var rect = section.getBoundingClientRect();
        return {
          title: section.querySelector("h2").textContent.replace(/\s+/g, " ").trim(),
          top: Math.round(rect.top)
        };
      }),
      blocks: [".stage", ".controls", ".hint", "#face-registry"].map(function (selector) {
        var rect = g(selector).getBoundingClientRect();
        return { selector: selector, top: Math.round(rect.top), bottom: Math.round(rect.bottom) };
      }),
      group_gap: (function () {
        var second = d.querySelectorAll(".section")[1];
        var style = css(second);
        return { margin_top: parseFloat(style.marginTop), padding_top: parseFloat(style.paddingTop) };
      })(),
      truncated: dd.filter(function (el) {
        return el.scrollWidth > el.clientWidth + 1;
      }).map(function (el) {
        return el.id + " " + el.scrollWidth + ">" + el.clientWidth;
      }),
      peak_truncated: (function () {
        var peak = g("#m-peak");
        return peak.scrollWidth > peak.clientWidth + 1;
      })(),
      controls: ["apply", "clear-roi", "view-source", "view-decoded", "snapshot", "record", "metrics"].map(function (id) {
        var rect = d.getElementById(id).getBoundingClientRect();
        return { id: id, bottom: Math.round(rect.bottom), on_first_screen: rect.bottom <= win.innerHeight + 0.5 };
      }),
      spark: (function () {
        var canvas = g("#spark");
        var rect = canvas.getBoundingClientRect();
        return {
          css_height: Math.round(rect.height),
          width: Math.round(rect.width),
          backing: [canvas.width, canvas.height],
          aria: canvas.getAttribute("aria-label")
        };
      })(),
      peak: { text: g("#m-peak").textContent },
      widest_right: Math.max.apply(null, elements.map(function (el) {
        return Math.round(el.getBoundingClientRect().right);
      })),
      stage: (function () {
        var rect = g(".stage").getBoundingClientRect();
        return { width: Math.round(rect.width), height: Math.round(rect.height) };
      })(),
      rail: (function () {
        var rect = g(".rail").getBoundingClientRect();
        return { width: Math.round(rect.width), height: Math.round(rect.height) };
      })(),
      registry_top: Math.round(g("#face-registry").getBoundingClientRect().top)
    };
  }

  function tick() {
    if (finished) return;
    attempts += 1;
    if (attempts > 200) {
      done({ error: "the framed page never became measurable" });
      return;
    }
    try {
      var payload = collect();
      if (payload) {
        done(payload);
        return;
      }
    } catch (error) {
      done({ error: String(error) });
      return;
    }
    setTimeout(tick, 40);
  }

  // Measured inside the frame's load handler, not on a timer: Chrome dumps the
  // DOM at the top-level load event, so anything scheduled after it is too late.
  frame.addEventListener("load", tick);
  tick();
})();
"""

WRAPPER = """<!DOCTYPE html>
<meta charset="utf-8">
<style>
  html, body {{ margin: 0; background: #000; overflow: hidden; }}
  iframe {{ display: block; width: {width}px; height: {height}px; border: 0; }}
  #report {{ position: fixed; left: -4000px; top: 0; margin: 0; }}
</style>
<iframe id="page" src="{src}"></iframe>
<pre id="report"></pre>
<script>{measure}</script>
"""


def prepare_copy() -> tuple[Path, dict]:
    """Save what the server serves, so a file on disk can be measured."""
    copy = HERE / "_copy"
    copy.mkdir(exist_ok=True)
    for name, url in (
        ("index.html", "/"),
        ("style.css", "/static/style.css"),
        ("app.js", "/static/app.js"),
    ):
        served = urlopen(BASE + url, timeout=10).read()
        (copy / name).write_bytes(served)
    served_html = (copy / "index.html").read_text(encoding="utf-8")
    css = (copy / "style.css").read_text(encoding="utf-8")
    link = '<link rel="stylesheet" href="/static/style.css" />'
    script = '<script src="/static/app.js"></script>'
    assert link in served_html and script in served_html, "the served page is not the one expected"
    measured = served_html.replace(link, "<style>\n" + css + "\n</style>")
    measured = measured.replace(script, "<!-- app.js dropped for the measurement pass -->")
    (copy / "index.measure.html").write_text(measured, encoding="utf-8")
    restored = (
        measured.replace("<style>\n" + css + "\n</style>", link)
        .replace("<!-- app.js dropped for the measurement pass -->", script)
    )
    assert restored == served_html, (
        "the copy differs from the served page by more than the two edits this probe declares"
    )
    return copy / "index.measure.html", {
        "served_index_sha256": hashlib.sha256(served_html.encode()).hexdigest(),
        "served_css_sha256": hashlib.sha256((copy / "style.css").read_bytes()).hexdigest(),
        "served_js_sha256": hashlib.sha256((copy / "app.js").read_bytes()).hexdigest(),
        "edits": [
            "the /static/style.css link is replaced by the same bytes in a <style> block, so the "
            "file on disk cannot render before its sheet arrives",
            "the app.js script tag is dropped: every number measured is a function of the "
            "stylesheet and the markup, and a live socket keeps Chrome --dump-dom from settling",
        ],
    }


def chrome(*arguments: str, timeout: int = 180) -> subprocess.CompletedProcess:
    profile = Path.home() / "AppData" / "Local" / "Temp" / ("rvm03-" + uuid.uuid4().hex[:10])
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
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def wrapper(width: int, height: int, source: str, measure_script: str = "") -> Path:
    path = HERE / f"_wrap-{width}x{height}-{abs(hash(source)) % 100000}.html"
    page = path.with_suffix(".html")
    page.write_text(
        WRAPPER.format(width=width, height=height, src=source, measure=measure_script),
        encoding="utf-8",
    )
    return page


def shot_wrapper(width: int, height: int) -> Path:
    return wrapper(width, height, BASE + "/")


def shoot(width: int, height: int, name: str) -> dict:
    page = shot_wrapper(width, height)
    png = HERE / name
    if png.exists():
        png.unlink()
    chrome(f"--window-size={width + 40},{height + 120}", f"--screenshot={png}", page.as_uri())
    if not png.exists():
        raise SystemExit(f"chrome produced no {name}")
    from PIL import Image

    cropped = Image.open(png).crop((0, 0, width, height))
    cropped.save(png)
    return {"path": name, "size": [cropped.width, cropped.height], "bytes": png.stat().st_size}


def measure(width: int, height: int, index: Path, override: str = "") -> dict:
    script = MEASURE.replace("__INJECT__", json.dumps(INJECT)).replace(
        "__OVERRIDE__", json.dumps(override)
    )
    for attempt in range(1, 4):
        page = wrapper(width, height, index.as_uri(), script)
        result = chrome(
            f"--window-size={width + 40},{height + 120}",
            "--allow-file-access-from-files",
            "--disable-web-security",
            "--dump-dom",
            page.as_uri(),
            timeout=45,
        )
        match = re.search(r"MEASURE:(\{.*?\})</pre>", result.stdout, re.S)
        if match:
            payload = json.loads(match.group(1))
            payload["attempt"] = attempt
            return payload
        print(f"  attempt {attempt}: no measurement, retrying", file=sys.stderr)
    raise SystemExit("the page could not be measured in three attempts")


def main() -> int:
    with urlopen(BASE + "/", timeout=10) as response:
        assert response.status == 200, response.status
    index, provenance = prepare_copy()
    report = {
        "base": BASE,
        "provenance": provenance,
        "shots": [],
        "desktop": measure(1440, 1000, index),
        "mobile": measure(390, 844, index),
        "mobile_two_column": measure(
            390, 844, index, override=".readouts{grid-template-columns:1fr 1fr !important}"
        ),
    }
    for width, height, name in VIEWPORTS:
        report["shots"].append(shoot(width, height, name))
    out = HERE / "03-dashboard-readability-selfcheck.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
