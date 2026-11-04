"""The streaming session: one encoder, many viewers.

This is the server side of the reference architecture the lecture gives --
capture, compress, and a transport interface feeding a network -- with the
analysis stages bolted on alongside.  One capture pipeline and one encoder feed
every viewer, which is what makes the system a *broadcast* rather than N
transcodings: the second viewer costs bandwidth, not CPU.

Two decisions are worth stating because they shape everything else.

**One encode, many clients.**  Transcoding per viewer was explicitly rejected
in favour of scalable coding, and since browsers cannot consume a scalable
bitstream directly, a single operating point plus rate control is the honest
choice for this project.

**Latest-only delivery.**  Each client holds a bounded queue that keeps only
the newest picture.  A live monitoring feed that delivers a backlog is worse
than useless -- by the time a slow client works through it, the information is
stale.  Dropping is the correct behaviour, and it is what keeps one slow
viewer from adding latency for everyone else.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path

import numpy as np

from ..analysis import states
from ..analysis.detect import FaceDetector, MotionDetector, sensitivity_settings
from ..analysis.gesture import GestureDetection, GestureRecognizer
from ..analysis.recognition import (
    EmotionDetection,
    EmotionRecognizer,
    FaceRecognition,
    FaceRecognizer,
)
from ..analysis.track import CentroidTracker, regions_from_mask
from ..analysis.quality import psnr
from ..audio import AudioAnalyzer, AudioCapture, AudioEvent
from ..codec.video import VideoEncoder
from ..core.colorspace import rgb_to_ycbcr, to_planes
from ..network.packet import Packet, frame_timestamp, packetize
from ..network.stats import StreamStats
from .recorder import FrameRecorder
from .source import CaptureSource, SyntheticSource

__all__ = ["ClientSession", "StreamSession"]

#: How many audio events stay on record; the dashboard shows the newest few.
AUDIO_EVENT_LIMIT = 50
#: Audio chunks consumed per analysis tick, so a burst cannot stall a picture.
AUDIO_CHUNKS_PER_TICK = 8


class ClientSession:
    """One connected viewer."""

    def __init__(self, client_id: str, max_queue: int = 4):
        self.id = client_id
        self.connected_at = time.time()
        self.packets_delivered = 0
        self.pictures_delivered = 0
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
        self._max_queue = max_queue

    async def get(self, timeout: float = 1.0) -> Packet | None:
        """Await the next packet, or ``None`` if nothing arrives in time."""
        try:
            packet = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return packet

    def offer(self, packets: list[Packet]) -> None:
        """Queue packets, discarding the backlog when the client falls behind."""
        for packet in packets:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - race only
                    pass
            self._queue.put_nowait(packet)
            self.packets_delivered += 1
            if packet.marker:
                self.pictures_delivered += 1

    def close(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover
                break


class StreamSession:
    """Owns the capture, encode and analysis pipeline for one camera."""

    def __init__(
        self,
        width: int = 320,
        height: int = 240,
        fps: float = 15.0,
        bitrate: int = 1_200_000,
        gop_size: int = 30,
        source: CaptureSource | None = None,
        motion_threshold: float = 0.01,
        record_dir: str | Path | None = None,
        analysis: bool = False,
        analysis_interval: float = 0.5,
    ) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        self.gop_size = gop_size
        self.record_dir = Path(record_dir) if record_dir else Path("recordings")

        self.source = source or SyntheticSource(width, height, fps)
        self.encoder = VideoEncoder(
            width, height, target_bitrate=bitrate, frame_rate=fps, gop_size=gop_size
        )
        self.motion_detector = MotionDetector(threshold=motion_threshold)
        # The operator can narrow detection to a region and choose how eager
        # the alarm is; defaults reproduce the behaviour with no controls used.
        self.roi: tuple[float, float, float, float] | None = None
        self.motion_sensitivity = "medium"
        self.face_detector = FaceDetector()
        self.tracker = CentroidTracker()

        # Optional analysis.  It is off unless asked for, because it is the one
        # part of the pipeline that costs tens of milliseconds per picture and
        # would otherwise make every test and every headless run pay for models
        # it never uses.
        self.analysis_enabled = analysis
        self.analysis_interval = analysis_interval
        self.face_recognizer = FaceRecognizer()
        self.emotion_recognizer = EmotionRecognizer()
        self.gesture_recognizer = GestureRecognizer()
        self.audio_analyzer = AudioAnalyzer()
        self.audio_capture: AudioCapture | None = None
        # A freshly enabled analyser has not seen a picture yet: "pending", not
        # "disabled", or the dashboard cannot tell "not started" from "off".
        initial_state = states.STATE_PENDING if analysis else states.STATE_DISABLED
        self._face_identities = FaceRecognition([], initial_state)
        self._emotions = EmotionDetection([], initial_state)
        self._gestures = GestureDetection([], initial_state)
        # One tuple, swapped atomically: readers never see a half-applied tick.
        self._analysis_view = (self._face_identities, self._emotions, self._gestures)
        self._audio_events: list[AudioEvent] = []
        self._models_ready = threading.Event()
        self._warmup: threading.Thread | None = None
        self._analysis_due = 0.0

        self.stats = StreamStats(window_seconds=4.0)
        self.recorder: FrameRecorder | None = None

        self._clients: dict[str, ClientSession] = {}
        self._sequence = 0
        self._frames = 0
        self._latest: np.ndarray | None = None
        self._latest_jpeg: bytes | None = None
        self._decoded_jpeg: bytes | None = None
        self._motion = None
        self._faces = None
        self._tracks: list = []
        self._psnr: float | None = None
        self._injected: np.ndarray | None = None
        self._lock = asyncio.Lock()

        if analysis:
            self._start_model_warmup()

    # -- client management ---------------------------------------------------

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def add_client(self, max_queue: int = 4) -> ClientSession:
        client = ClientSession(uuid.uuid4().hex[:12], max_queue=max_queue)
        self._clients[client.id] = client
        return client

    def remove_client(self, client_id: str) -> None:
        client = self._clients.pop(client_id, None)
        if client is not None:
            client.close()

    # -- configuration -------------------------------------------------------

    def update_config(self, bitrate: int | None = None, gop_size: int | None = None) -> None:
        if bitrate is not None and bitrate <= 0:
            raise ValueError(f"bitrate must be positive, got {bitrate}")
        if gop_size is not None and gop_size <= 0:
            raise ValueError(f"gop_size must be positive, got {gop_size}")

        if bitrate is not None and bitrate != self.bitrate:
            self.bitrate = bitrate
            self.encoder.rate_controller.target_bitrate = bitrate
            self.encoder.rate_controller.reset()
        if gop_size is not None:
            self.gop_size = gop_size
            self.encoder.gop_size = gop_size

    def configure_recording(self, enabled: bool) -> None:
        """Start or finish a time-stamped clip."""
        if enabled and self.recorder is None:
            self.recorder = FrameRecorder(self.record_dir, fps=self.fps)
        elif not enabled and self.recorder is not None:
            self.recorder.stop()
            self.recorder = None

    def set_roi(self, roi) -> None:
        """Confine motion detection to a normalised region, or clear it.

        Clearing the scene's history is part of the change, not a side effect:
        the background model was learnt with a different definition of "the
        monitored area", and keeping it would leave the alarm comparing
        apples with oranges for the first seconds after the operator draws a
        box.
        """
        if roi is None:
            self.roi = None
        else:
            # Validating through the detector keeps one definition of a legal
            # region rather than two that can drift apart.
            MotionDetector._bounds(roi, (self.height, self.width))
            self.roi = tuple(float(value) for value in roi)
        self.motion_detector.reset()
        self.tracker.reset()
        self._tracks = []

    def set_motion_sensitivity(self, name: str) -> None:
        """Pick how eager the motion alarm is: ``low``, ``medium`` or ``high``."""
        self.motion_detector.configure(**sensitivity_settings(name))
        self.motion_sensitivity = name
        self.tracker.reset()
        self._tracks = []

    @property
    def recording(self) -> bool:
        return self.recorder is not None

    def inject_frame(self, frame: np.ndarray) -> None:
        """Force the next picture to be ``frame``; used by tests and demos."""
        self._injected = np.asarray(frame)

    def record_feedback(self, feedback: dict) -> None:
        """Apply delivery feedback from a receiver.

        The server counts what it sent but cannot know what arrived, so loss
        and jitter only mean anything once a client reports back. That report
        is the feedback half of the control loop the lecture describes.
        """
        received = feedback.get("received")
        lost = feedback.get("lost")
        if isinstance(received, int) and isinstance(lost, int):
            self.stats.record_feedback(received=received, lost=lost)
        jitter_ms = feedback.get("jitter_ms")
        if isinstance(jitter_ms, (int, float)):
            self.stats.record_jitter_ms(jitter_ms)

    # -- pipeline ------------------------------------------------------------

    async def run_once(self):
        """Capture, analyse and encode one picture, then fan it out.

        The work is handed to a worker thread.  Coding one picture is tens of
        milliseconds of solid arithmetic, and doing that inside the event loop
        would stop the server answering the dashboard, serving the stream and
        pushing telemetry for exactly as long as it takes.  NumPy and OpenCV
        release the interpreter lock for the heavy parts, so the loop keeps
        running while the encoder works.
        """
        async with self._lock:
            return await asyncio.to_thread(self._encode_once)

    def _encode_once(self):
        """The blocking half of :meth:`run_once`; runs in a worker thread."""
        frame = self._next_frame()
        if frame is None:
            return None

        luma = to_planes(rgb_to_ycbcr(frame))[0].astype(np.uint8)

        self._motion = self.motion_detector.update(luma, roi=self.roi)
        self._faces = self.face_detector.detect(luma)
        self._tracks = self.tracker.update(regions_from_mask(self._motion.mask))

        self._analyse(frame)
        self._drain_audio()

        encoded = self.encoder.encode(frame)

        # Quality is measured against the encoder's own reconstruction,
        # which is exactly what the receiver will display. Comparing the
        # source against itself would report an infinite PSNR and say
        # nothing at all about what the codec cost.
        reconstruction = self.encoder.reconstruction_luma
        if reconstruction is not None:
            self._psnr = psnr(luma, reconstruction.astype(np.uint8))

        now = time.monotonic()
        packets = packetize(
            encoded.data,
            sequence=self._sequence,
            timestamp=frame_timestamp(encoded.frame_index, self.fps),
            max_payload=1200,
        )
        self._sequence += len(packets)

        for packet in packets:
            self.stats.record_sent(packet, now=now, is_keyframe=encoded.is_keyframe)
            for client in list(self._clients.values()):
                client.offer([packet])

        self._frames += 1
        self._latest = frame
        self._latest_jpeg = self._encode_jpeg(frame)

        # The decoded view is the picture a receiver reconstructs from the
        # bitstream.  Publishing it next to the source view lets the operator
        # see the codec's own distortion instead of being told about it.
        reconstruction_rgb = self.encoder.reconstruction_rgb
        if reconstruction_rgb is not None:
            self._decoded_jpeg = self._encode_jpeg(reconstruction_rgb)

        if self.recorder is not None:
            self.recorder.write(frame, timestamp=encoded.timestamp)

        return encoded

    def _next_frame(self) -> np.ndarray | None:
        if self._injected is not None:
            frame, self._injected = self._injected, None
            return frame
        return self.source.read()

    @staticmethod
    def _encode_jpeg(frame: np.ndarray) -> bytes | None:
        try:
            import cv2

            ok, buffer = cv2.imencode(".jpg", frame[:, :, ::-1])
            return buffer.tobytes() if ok else None
        except Exception:  # noqa: BLE001
            return None

    # -- optional analysis ---------------------------------------------------

    def _start_model_warmup(self) -> None:
        """Load the MediaPipe bundles off the encode thread.

        Creating a landmarker reads a multi-megabyte model; doing that inside
        :meth:`_encode_once` would hold the first picture of the stream for
        seconds.  The encode thread waits on :attr:`_models_ready` instead, so
        the stream starts immediately and the analyzers join once they can.
        """

        def warm_up() -> None:
            for recognizer in (
                self.face_recognizer,
                self.emotion_recognizer,
                self.gesture_recognizer,
            ):
                try:
                    recognizer.available  # noqa: B018 - forces the load
                except Exception:  # noqa: BLE001 - a missing model is not fatal
                    pass
            # Probe the microphone here too: opening PortAudio costs ~300 ms
            # and doing it from ``status()`` would stall the telemetry push.
            try:
                self._audio_capture().available
            except Exception:  # noqa: BLE001 - no audio is not fatal either
                pass
            self._models_ready.set()

        self._warmup = threading.Thread(
            target=warm_up, name="rvm-model-warmup", daemon=True
        )
        self._warmup.start()

    def _analyse(self, frame: np.ndarray) -> None:
        """Run the optional analysers on a cadence rather than per picture.

        Encoding one 320x240 picture costs 34-49 ms on the demonstration
        machine, and one analysis pass costs 19-35 ms.  Running the analysers
        per frame would therefore add roughly a third to every picture to
        refresh a dashboard panel; every ``analysis_interval`` seconds costs
        4-7 % of the encoder's time instead.

        The three results are published as one tuple so a reader never sees a
        half-applied tick (face updated, gestures still pending).
        """
        if not self.analysis_enabled or not self._models_ready.is_set():
            return

        now = time.monotonic()
        if now < self._analysis_due:
            return
        self._analysis_due = now + self.analysis_interval

        face_identities = self.face_recognizer.recognize(frame)
        emotions = self.emotion_recognizer.detect(frame)
        gestures = self.gesture_recognizer.detect(frame)
        self._analysis_view = (face_identities, emotions, gestures)

    def _drain_audio(self) -> None:
        """Move captured audio into events, a bounded number of chunks at a time.

        Deliberately *not* behind the analysis gate: audio monitoring is a
        separate switch.  Gating it there made ``POST /api/audio/control``
        report a running microphone that could never produce an event.
        """
        capture = self.audio_capture
        if capture is None or not capture.running:
            return

        # Rebind rather than mutate: ``status()`` slices this list from another
        # thread, and an in-place ``extend`` can hand it a half-updated list.
        events = list(self._audio_events)
        for _ in range(AUDIO_CHUNKS_PER_TICK):
            chunk = capture.read(timeout=0.0)
            if chunk is None:
                break
            events.extend(self.audio_analyzer.analyze(chunk))
        self._audio_events = events[-AUDIO_EVENT_LIMIT:]

    def _audio_capture(self) -> AudioCapture:
        """The microphone, created on first use so a headless run pays nothing."""
        if self.audio_capture is None:
            self.audio_capture = AudioCapture()
        return self.audio_capture

    @property
    def audio_enabled(self) -> bool:
        """Whether the microphone is actually capturing right now."""
        return self.audio_capture is not None and self.audio_capture.running

    def set_audio_enabled(self, enabled: bool) -> bool:
        """Start or stop audio monitoring; returns whether it is running.

        Blocking: opening PortAudio costs a few hundred milliseconds, so call
        this from a worker thread (the HTTP handler does).  The device probe
        happens here for the same reason -- and so that the answer about the
        device is never "never looked".
        """
        capture = self._audio_capture()
        capture.available
        if enabled:
            if capture.start():
                # A fresh start is a fresh measurement: leftover RMS history
                # would let the first chunk of a new session look like the
                # continuation of an alarm.
                self.audio_analyzer.reset()
                self._audio_events = []
                capture.clear_buffer()
        else:
            capture.stop()
        return self.audio_enabled

    def audio_report(self, requested: bool) -> dict:
        """Apply an audio-control request and describe the outcome.

        One method so that the whole blocking interaction -- probe, open,
        report -- is a single hop to a worker thread instead of the response
        being assembled on the event loop, where the first probe alone stalls
        every other request for ~300 ms.
        """
        running = self.set_audio_enabled(requested)
        capture = self.audio_capture
        return {
            "requested": requested,
            "running": running,
            "available": bool(capture and capture.available),
            "reason": None if capture is None else capture.unavailable_reason,
        }

    def features(self) -> dict:
        """Which optional analysers this machine can actually run.

        Availability is reported from what has already been probed rather than
        by probing here: ``status()`` calls this twice a second, and opening
        PortAudio or a MediaPipe model on that path would stall the telemetry
        push for hundreds of milliseconds.  ``audio_available`` is therefore
        ``None`` until the warm-up thread (or an audio-control request) has
        looked.
        """
        ready = self.analysis_enabled and self._models_ready.is_set()
        return {
            "enabled": self.analysis_enabled,
            "ready": self._models_ready.is_set(),
            "face_recognition": ready and self.face_recognizer.available,
            "emotion_recognition": ready and self.emotion_recognizer.available,
            "gesture_recognition": ready and self.gesture_recognizer.available,
            "audio_monitoring": self.audio_enabled,
            "audio_available": (
                None if self.audio_capture is None else self.audio_capture.availability
            ),
        }

    def analysis_status(self) -> dict:
        """The analysis half of the API, in one shape for every caller."""
        face_identities, emotions, gestures = self._analysis_view
        return {
            "tracks": {
                "count": len(self._tracks),
                "tracks": [track.snapshot() for track in self._tracks],
            },
            "face_identities": face_identities.snapshot(),
            "emotions": emotions.snapshot(),
            "gestures": gestures.snapshot(),
            "audio": {
                "count": len(self._audio_events),
                "events": [event.snapshot() for event in self._audio_events[-20:]],
                "running": self.audio_enabled,
            },
            "features": self.features(),
        }

    # -- outputs -------------------------------------------------------------

    def snapshot_jpeg(self, view: str = "source") -> bytes | None:
        """The most recent picture as a JPEG.

        ``view="source"`` is the raw camera picture; ``view="decoded"`` is the
        picture reconstructed from the coded bitstream, i.e. what a remote
        station receives after the codec has done its work.
        """
        if view == "decoded":
            return self._decoded_jpeg
        return self._latest_jpeg

    async def wait_for_picture(
        self, view: str = "source", timeout: float = 2.0
    ) -> bytes | None:
        """Wait for the first picture to exist, then return it.

        The server needs a moment to produce its first picture after it
        starts.  A client that asks during that moment is better served by
        waiting briefly than by being told the picture does not exist.
        """
        deadline = time.monotonic() + timeout
        while True:
            jpeg = self.snapshot_jpeg(view=view)
            if jpeg is not None:
                return jpeg
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.02)

    def latest_frame(self) -> np.ndarray | None:
        return self._latest

    def status(self) -> dict:
        """A JSON-friendly summary for the dashboard and the REST API."""
        face_identities, emotions, gestures = self._analysis_view
        snapshot = self.stats.snapshot()
        motion = self._motion.snapshot() if self._motion else {}
        faces = self._faces.snapshot() if self._faces else {}
        snapshot.update(
            {
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "bitrate_target": self.bitrate,
                "qp": self.encoder.rate_controller.current_qp,
                "frames": self._frames,
                "clients": self.client_count,
                "recording": self.recording,
                "source": self.source.name,
                "psnr": round(self._psnr, 2) if self._psnr is not None else None,
                "frame_rate": round(snapshot.get("frame_rate", 0.0), 2),
                # Motion state is flattened as well as nested: the dashboard
                # reads these on every tick, and a nested lookup per field is
                # noise in the hot path.
                "alarm": bool(motion.get("alarm", False)),
                "motion_ratio": motion.get("motion_ratio", 0.0),
                "bbox": motion.get("bbox"),
                "faces": faces.get("count", 0),
                "roi": list(self.roi) if self.roi else None,
                "motion_sensitivity": self.motion_sensitivity,
                "motion": motion,
                "tracks": [track.snapshot() for track in self._tracks],
                # The analysis results ride along with the telemetry the
                # WebSocket already pushes, so the dashboard needs no second
                # polling loop to show them.
                "face_identities": face_identities.snapshot(),
                "emotions": emotions.snapshot(),
                "gestures": gestures.snapshot(),
                "audio_events": len(self._audio_events),
                "audio_last": (
                    self._audio_events[-1].event_type.value if self._audio_events else None
                ),
                "analysis": self.features(),
            }
        )
        return snapshot

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        """Capture and encode until asked to stop, pacing to the frame rate."""
        stop = stop or asyncio.Event()
        period = 1.0 / self.fps if self.fps > 0 else 0.04

        while not stop.is_set():
            started = time.monotonic()
            await self.run_once()
            remaining = period - (time.monotonic() - started)
            if remaining > 0:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    pass

    def close(self) -> None:
        for client in list(self._clients.values()):
            client.close()
        self._clients.clear()
        if self.recorder is not None:
            self.recorder.stop()
            self.recorder = None
        if self.audio_capture is not None:
            self.audio_capture.close()
            self.audio_capture = None

        # The warm-up thread may still be loading models; releasing them while
        # it runs would race with the loader.
        if self._warmup is not None and self._warmup.is_alive():
            self._warmup.join(timeout=5.0)
        for recognizer in (
            self.face_recognizer,
            self.emotion_recognizer,
            self.gesture_recognizer,
        ):
            recognizer.close()

        self.source.close()

