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

/* Values that have not arrived yet carry a placeholder class; writing a real
 * value drops it, so the grey hyphen never survives the first telemetry frame. */
function setText(id, value) {
  const node = $(id);
  if (!node) return;
  if (node.textContent !== value) node.textContent = value;
  if (value !== "-" && node.classList.contains("pending")) node.classList.remove("pending");
}

function fmtBitrate(bps) {
  if (!bps) return "0 bps";
  if (bps >= 1e6) return (bps / 1e6).toFixed(2) + " Mbps";
  if (bps >= 1e3) return (bps / 1e3).toFixed(0) + " kbps";
  return bps + " bps";
}

/* The tag beside the trace names the magnitude the plot is scaled to, so it is
 * always two decimals and a unit rather than a formatted value with a moving
 * unit: the label has to be the same number on every frame. */
function fmtPeak(bps) {
  return bps > 0 ? "peak " + (bps / 1e6).toFixed(2) + " Mbps" : "peak -";
}

/* An analyser that is switched off must not look like one that is broken, one
 * that is still starting must not look like one that is off, and one that is
 * working on an empty scene must not look like either. The state the server
 * reports is what separates those cases. */
function analysisText(result, field, emptyLabel, limit = 3) {
  if (!result) return "-";
  const state = result.state;
  if (state === "disabled") return "off";
  if (state === "pending") return "loading";
  if (state === "unavailable") return "unavailable";
  if (state === "error") return "error";
  if (state === "no-known-faces") {
    return result.seen ? result.seen + " face, none known" : "no known faces";
  }
  if (!result.count) return emptyLabel;
  return result[field]
    .slice(0, limit)
    .map((item) => item.gesture || item.emotion || item.name || "?")
    .join(", ");
}

function render(s) {
  lastStatus = s;
  setText("m-res", s.width + "×" + s.height);
  setText("m-fps", (s.frame_rate ?? 0).toFixed(1) + " fps");
  setText("m-bitrate", fmtBitrate(s.bitrate));
  setText("m-qp", s.qp ?? "-");
  setText("m-psnr", s.psnr == null ? "-" : s.psnr + " dB");
  setText("m-pkts", s.packets_sent ?? 0);
  setText("m-pics", s.pictures ?? 0);
  setText("m-loss", ((s.fraction_lost ?? 0) * 100).toFixed(2) + " %");
  setText("m-jitter", (s.jitter_ms ?? 0).toFixed(2) + " ms");
  setText("m-clients", s.clients ?? 0);
  setText("m-motion", ((s.motion_ratio ?? 0) * 100).toFixed(2) + " %");
  setText("m-faces", s.faces ?? 0);
  setText(
    "m-tracks",
    (s.tracks || []).length ? (s.tracks || []).map((t) => "T" + t.id).join(", ") : "none"
  );
  setText("m-gestures", analysisText(s.gestures, "gestures", "no hand"));
  setText("m-emotions", analysisText(s.emotions, "emotions", "no face"));
  setText("m-identities", analysisText(s.face_identities, "identities", "no face"));
  setText("m-audio", s.audio_last || (s.audio_events ? s.audio_events + " events" : "none"));
  setText("m-rec", s.recording ? "recording" : "off");
  setText("src-label", "source: " + (s.source || "-"));

  $("alarm").classList.toggle("on", Boolean(s.alarm));
  setText("m-roi", s.roi ? "custom zone" : "whole picture");
  drawRegion(s);
  drawMotionBox(s);
  drawTracks(s);
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

/* Each tracked object gets an ID tag at its centre and a fading dotted trail
 * of where it has been, in the same percentage coordinates as the zone box. */
function drawTracks(s) {
  const box = $("tracks");
  const nodes = [];
  const w = s.width || 1;
  const h = s.height || 1;

  for (const track of s.tracks || []) {
    const trail = track.trail || [];
    trail.forEach((point, i) => {
      const dot = document.createElement("i");
      dot.className = "track-dot";
      dot.style.left = ((point[0] / w) * 100).toFixed(2) + "%";
      dot.style.top = ((point[1] / h) * 100).toFixed(2) + "%";
      dot.style.opacity = (0.2 + (0.8 * (i + 1)) / trail.length).toFixed(2);
      nodes.push(dot);
    });

    if (track.centroid) {
      const tag = document.createElement("b");
      tag.className = "track-tag";
      tag.textContent = "T" + track.id;
      tag.style.left = ((track.centroid[0] / w) * 100).toFixed(2) + "%";
      tag.style.top = ((track.centroid[1] / h) * 100).toFixed(2) + "%";
      nodes.push(tag);
    }
  }

  box.replaceChildren(...nodes);
}

/* The trace is normalised to the maximum of its own window and the tag beside
 * the chart prints that same maximum, so the height of the line is a number the
 * reader can check instead of a shape with no units. The dashed rule sits at
 * the peak's own scale position; it is muted grey rather than the accent so it
 * cannot be read as a second series. */
function drawSpark() {
  const canvas = $("spark");
  const ctx = canvas.getContext("2d");
  const values = history.bitrate;
  const box = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(box.width * ratio));
  const height = Math.max(1, Math.round(box.height * ratio));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  ctx.clearRect(0, 0, width, height);

  if (!values.length) {
    setText("m-peak", "peak -");
    return;
  }

  const peak = Math.max(...history.bitrate) || 1;

  const floor = 3 * ratio;      // the baseline the trace stands on
  const ceiling = 6 * ratio;    // the dashed rule: the peak's scale position
  const headroom = 4 * ratio;   // air between the rule and the apex
  const band = Math.max(1, height - floor - ceiling - headroom);

  ctx.save();
  ctx.setLineDash([3 * ratio, 3 * ratio]);
  ctx.beginPath();
  ctx.moveTo(0, Math.round(ceiling) + 0.5);
  ctx.lineTo(width, Math.round(ceiling) + 0.5);
  ctx.strokeStyle = "rgba(154,165,170,.5)";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();

  if (values.length === 1) {
    // One sample is still a window with a peak: a dot on the rule, so the scale
    // the tag names is on screen from the first telemetry frame onwards.
    const y = height - floor - (values[0] / peak) * band;
    ctx.beginPath();
    ctx.arc(2 * ratio, y, 2 * ratio, 0, Math.PI * 2);
    ctx.fillStyle = "#5fd3c6";
    ctx.fill();
  } else {
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = (i / (history.max - 1)) * width;
      const y = height - floor - (v / peak) * band;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = "#5fd3c6";
    ctx.lineWidth = 2 * ratio;
    ctx.lineJoin = "round";
    ctx.stroke();
  }

  // A hairline floor, so the trace reads as a chart rather than a squiggle.
  ctx.beginPath();
  ctx.moveTo(0, height - 0.5);
  ctx.lineTo(width, height - 0.5);
  ctx.strokeStyle = "#252c30";
  ctx.lineWidth = 1;
  ctx.stroke();

  setText("m-peak", fmtPeak(peak));
  canvas.setAttribute(
    "aria-label",
    "Recent video bitrate history, scaled to a peak of " + (peak / 1e6).toFixed(2) + " Mbps"
  );
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
  // The pressed side of the toggle is the visible state; the aria-pressed pair
  // and the screen-reader mirror say the same thing without a second label.
  for (const [id, name] of [
    ["view-source", "source"],
    ["view-decoded", "decoded"],
  ]) {
    const button = $(id);
    button.classList.toggle("active", view === name);
    button.setAttribute("aria-pressed", view === name ? "true" : "false");
  }
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

/* 20261024_213812 reads as 2026-10-24 21:38, which is what the operator says
 * out loud when asked which clip to open. */
function clipLabel(name) {
  const date = name.slice(0, 8);
  const time = name.slice(9, 15);
  return (
    date.slice(0, 4) + "-" + date.slice(4, 6) + "-" + date.slice(6, 8) +
    " " + time.slice(0, 2) + ":" + time.slice(2, 4)
  );
}

function renderClips(clips) {
  const list = $("clips");
  // Only names the recorder could have produced reach the DOM: the panel is
  // built with innerHTML, and a stray file dropped into the recordings folder
  // must not be able to put markup on the operator's screen.
  const recent = clips
    .filter((clip) => /^\d{8}_\d{6}$/.test(clip.name))
    .slice(-5)
    .reverse();
  if (!recent.length) {
    list.innerHTML = '<li class="empty">No recording yet</li>';
    return;
  }
  list.innerHTML = recent
    .map((clip) => {
      const src = "/api/clips/" + clip.name + "/0.jpg";
      return (
        '<li><a href="' + src + '" target="_blank" rel="noopener">' +
        '<img src="' + src + '" alt="first frame of ' + clip.name + '" loading="lazy" />' +
        '<span class="clip-meta"><span class="clip-name">' + clipLabel(clip.name) + "</span>" +
        '<span class="clip-sub">' + clip.frames + " frames</span></span></a></li>"
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
