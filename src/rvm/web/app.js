/* Operator view for the remote video monitor.
 *
 * The picture comes from the MJPEG endpoint because a browser cannot decode the
 * project's custom RVM1 bitstream. The telemetry comes over a WebSocket, which
 * is the same socket that would carry the coded stream, so the numbers on
 * screen are the real ones from the transport layer rather than a separate
 * polling path that could disagree with it.
 */
"use strict";

const $ = (id) => document.getElementById(id);

const history = { bitrate: [], max: 60 };

function setText(id, value) {
  const node = $(id);
  if (node && node.textContent !== value) node.textContent = value;
}

function fmtBitrate(bps) {
  if (!bps) return "0 bps";
  if (bps >= 1e6) return (bps / 1e6).toFixed(2) + " Mbps";
  if (bps >= 1e3) return (bps / 1e3).toFixed(0) + " kbps";
  return bps + " bps";
}

function render(s) {
  lastStatus = s;
  setText("m-res", s.width + "×" + s.height);
  setText("m-fps", (s.frame_rate ?? 0).toFixed(1) + " fps");
  setText("m-bitrate", fmtBitrate(s.bitrate));
  setText("m-qp", s.qp ?? "—");
  setText("m-psnr", s.psnr == null ? "—" : s.psnr + " dB");
  setText("m-pkts", s.packets_sent ?? 0);
  setText("m-pics", s.pictures ?? 0);
  setText("m-loss", ((s.fraction_lost ?? 0) * 100).toFixed(2) + " %");
  setText("m-jitter", (s.jitter_ms ?? 0).toFixed(2) + " ms");
  setText("m-clients", s.clients ?? 0);
  setText("m-motion", ((s.motion_ratio ?? 0) * 100).toFixed(2) + " %");
  setText("m-faces", s.faces ?? 0);
  setText("m-rec", s.recording ? "recording" : "off");
  setText("src-label", "source: " + (s.source || "—"));

  $("alarm").classList.toggle("on", Boolean(s.alarm));
  setText("m-roi", s.roi ? "custom zone" : "whole picture");
  drawRegion(s);
  drawMotionBox(s);
  if (s.motion_sensitivity) $("sensitivity").value = s.motion_sensitivity;

  history.bitrate.push(s.bitrate ?? 0);
  if (history.bitrate.length > history.max) history.bitrate.shift();
  drawSpark();
}

/* The two boxes are drawn in percentages of the picture, so they stay glued to
 * the scene no matter how the browser scales the stream. */
function placeBox(node, x1, y1, x2, y2) {
  node.hidden = false;
  node.style.left = (x1 * 100).toFixed(2) + "%";
  node.style.top = (y1 * 100).toFixed(2) + "%";
  node.style.width = ((x2 - x1) * 100).toFixed(2) + "%";
  node.style.height = ((y2 - y1) * 100).toFixed(2) + "%";
}

function drawRegion(s) {
  const node = $("roi");
  if (!s.roi) {
    node.hidden = true;
    return;
  }
  placeBox(node, s.roi[0], s.roi[1], s.roi[2], s.roi[3]);
}

function drawMotionBox(s) {
  const node = $("bbox");
  if (!s.alarm || !s.bbox || !s.width || !s.height) {
    node.hidden = true;
    return;
  }
  const [top, left, bottom, right] = s.bbox;
  placeBox(node, left / s.width, top / s.height, right / s.width, bottom / s.height);
}

function drawSpark() {
  const canvas = $("spark");
  const ctx = canvas.getContext("2d");
  const values = history.bitrate;
  const scale = Math.max(1, ...values);

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (values.length < 2) return;

  ctx.beginPath();
  values.forEach((v, i) => {
    const x = (i / (history.max - 1)) * canvas.width;
    const y = canvas.height - (v / scale) * (canvas.height - 6) - 3;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.strokeStyle = "#4f9cf9";
  ctx.lineWidth = 2;
  ctx.stroke();

  setText("m-bitrate", fmtBitrate(values[values.length - 1]));
}

function tickClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  setText("time-label", `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`);
}

/* ---- transport ---------------------------------------------------------- */

let socket = null;
let retry = 0;

function connect() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${scheme}://${location.host}/ws`);

  socket.onopen = () => {
    retry = 0;
    $("conn").querySelector(".dot").className = "dot live";
    setText("conn-text", "live");
  };

  socket.onmessage = (event) => {
    try {
      render(JSON.parse(event.data));
    } catch (err) {
      /* a malformed frame must not take the dashboard down */
    }
  };

  socket.onclose = () => {
    $("conn").querySelector(".dot").className = "dot down";
    setText("conn-text", "reconnecting");
    retry = Math.min(retry + 1, 6);
    setTimeout(connect, 500 * retry);
  };

  socket.onerror = () => socket.close();
}

/* ---- picture source ----------------------------------------------------- */

/* "source" is the raw camera picture, "decoded" is the picture reconstructed
 * from the project's own RVM1 bitstream -- what a receiver really gets after
 * the codec has done its work. Switching between them during a demonstration
 * shows the codec's own distortion instead of describing it.
 */
let view = "source";

function setView(next) {
  view = next === "decoded" ? "decoded" : "source";
  const image = $("stream");
  // The cache-buster forces the browser to open a fresh multipart stream
  // instead of reusing the previous one.
  image.src = "/api/stream.mjpg?view=" + view + "&t=" + Date.now();
  $("view-source").classList.toggle("active", view === "source");
  $("view-decoded").classList.toggle("active", view === "decoded");
  setText("view-label", view === "decoded" ? "decoded (RVM1)" : "camera");
}

/* ---- controls ----------------------------------------------------------- */

async function postJSON(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function wire() {
  $("apply").onclick = async () => {
    try {
      render(await postJSON("/api/config", { bitrate: Number($("bitrate").value) }));
    } catch (err) {
      alert("Could not apply settings: " + err.message);
    }
  };

  $("snapshot").onclick = () => {
    const link = document.createElement("a");
    link.href = "/api/snapshot.jpg?view=" + view + "&t=" + Date.now();
    link.download = "snapshot-" + view + ".jpg";
    link.click();
  };

  $("view-source").onclick = () => setView("source");
  $("view-decoded").onclick = () => setView("decoded");

  const record = $("record");
  record.onclick = async () => {
    const start = !record.classList.contains("active");
    try {
      render(await postJSON("/api/record", { recording: start }));
      record.classList.toggle("active", start);
      record.textContent = start ? "Stop recording" : "Start recording";
    } catch (err) {
      alert("Could not toggle recording: " + err.message);
    }
  };

  $("metrics").onclick = () => {
    window.location.href = "/api/metrics";
  };

  $("stream").onerror = () => {
    $("stream").src = "/api/stream.mjpg?view=" + view + "&t=" + Date.now();
  };

  $("sensitivity").onchange = async (event) => {
    try {
      render(await postJSON("/api/motion", { sensitivity: event.target.value }));
    } catch (err) {
      alert("Could not change the sensitivity: " + err.message);
    }
  };

  $("clear-roi").onclick = async () => {
    try {
      render(await postJSON("/api/motion", { roi: null }));
    } catch (err) {
      alert("Could not clear the zone: " + err.message);
    }
  };
}

/* ---- detection zone ----------------------------------------------------- */

/* Dragging on the picture asks the server to watch only that rectangle. The
 * server does the confining -- the box here is only the operator's way of
 * saying where -- so a refresh or a second viewer sees the same zone. */
let dragStart = null;
let lastStatus = null;

function fractionAt(event) {
  const rect = $("stream").getBoundingClientRect();
  const x = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
  const y = Math.min(Math.max(event.clientY - rect.top, 0), rect.height);
  return rect.width && rect.height ? [x / rect.width, y / rect.height] : [0, 0];
}

function wireZone() {
  const stage = $("stage");

  stage.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button")) return;
    dragStart = fractionAt(event);
    stage.setPointerCapture(event.pointerId);
  });

  stage.addEventListener("pointermove", (event) => {
    if (!dragStart) return;
    const [x, y] = fractionAt(event);
    placeBox(
      $("roi"),
      Math.min(dragStart[0], x),
      Math.min(dragStart[1], y),
      Math.max(dragStart[0], x),
      Math.max(dragStart[1], y)
    );
  });

  stage.addEventListener("pointerup", async (event) => {
    if (!dragStart) return;
    const [x, y] = fractionAt(event);
    const region = [
      Math.min(dragStart[0], x),
      Math.min(dragStart[1], y),
      Math.max(dragStart[0], x),
      Math.max(dragStart[1], y),
    ];
    dragStart = null;

    // A click rather than a drag: leave the existing zone alone.
    if ((region[2] - region[0]) * (region[3] - region[1]) < 0.01) {
      if (lastStatus) drawRegion(lastStatus);
      return;
    }

    try {
      render(await postJSON("/api/motion", { roi: region }));
    } catch (err) {
      alert("Could not set the zone: " + err.message);
    }
  });
}

/* ---- recorded clips ----------------------------------------------------- */

/* The clip list is a convenience: a failure here must never disturb a live
 * picture, so the fetch swallows its own errors. */
async function pollClips() {
  try {
    const response = await fetch("/api/clips", { cache: "no-store" });
    const data = await response.json();
    renderClips(data.clips || []);
  } catch (err) {
    /* keep the old list rather than blanking the panel */
  }
}

function renderClips(clips) {
  const list = $("clips");
  const recent = clips.slice(-5).reverse();
  if (!recent.length) {
    list.innerHTML = '<li class="muted">No recording yet.</li>';
    return;
  }
  list.innerHTML = recent
    .map((clip) => {
      const src = "/api/clips/" + clip.name + "/0.jpg";
      return (
        '<li><a href="' + src + '" target="_blank" rel="noopener">' +
        '<img src="' + src + '" alt="first frame of ' + clip.name + '" loading="lazy" />' +
        "<span>" + clip.name.replace("_", " ") + "<br /><small>" +
        clip.frames + " frames</small></span></a></li>"
      );
    })
    .join("");
}

/* ---- start -------------------------------------------------------------- */

wire();
wireZone();
setView("source");
connect();
pollClips();
setInterval(pollClips, 3000);
tickClock();
setInterval(tickClock, 1000);
setInterval(() => {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send("ping");
}, 5000);