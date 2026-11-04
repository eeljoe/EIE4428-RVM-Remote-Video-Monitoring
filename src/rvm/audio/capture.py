"""Microphone capture in a worker thread, with a bounded hand-off queue."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Optional

import numpy as np

__all__ = ["AudioConfig", "AudioCapture"]

log = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """Capture settings; 16 kHz mono is enough to recognise speech events."""

    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    format: str = "int16"

    @property
    def chunk_duration_ms(self) -> float:
        """Duration of one chunk in milliseconds."""
        return (self.chunk_size / self.sample_rate) * 1000.0


class AudioCapture:
    """A microphone stream feeding a bounded queue of int16 chunks."""

    def __init__(self, config: Optional[AudioConfig] = None) -> None:
        self.config = config or AudioConfig()
        self._stream = None
        self._pyaudio = None
        self._capture_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._queue: Queue = Queue(maxsize=100)
        self._running = False
        self._failure: str | None = None

    @property
    def available(self) -> bool:
        """Whether a microphone can actually be opened on this machine."""
        return self._pyaudio is not None or (
            self._failure is None and self._init_pyaudio()
        )

    @property
    def unavailable_reason(self) -> str | None:
        if self._failure is None and self._pyaudio is None:
            self._init_pyaudio()
        return self._failure

    @property
    def running(self) -> bool:
        return self._running

    def _init_pyaudio(self) -> bool:
        if self._pyaudio is not None:
            return True
        if self._failure is not None:
            return False

        try:
            import pyaudio

            self._pyaudio = pyaudio.PyAudio()
            return True
        except Exception as exc:  # noqa: BLE001 - missing module or no device
            self._failure = f"{type(exc).__name__}: {exc}"
            log.info("audio capture unavailable: %s", self._failure)
            return False

    def start(self) -> bool:
        """Open the device and begin capturing; returns whether it started."""
        if self._running:
            return True
        if not self._init_pyaudio():
            return False

        try:
            import pyaudio

            formats = {
                "int16": pyaudio.paInt16,
                "int32": pyaudio.paInt32,
                "float32": pyaudio.paFloat32,
            }
            self._stream = self._pyaudio.open(
                format=formats.get(self.config.format, pyaudio.paInt16),
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                frames_per_buffer=self.config.chunk_size,
            )
            self._stop_event.clear()
            self._capture_thread = Thread(target=self._capture_loop, daemon=True)
            self._capture_thread.start()
            self._running = True
            return True
        except Exception as exc:  # noqa: BLE001 - no default input device is normal
            self._failure = f"{type(exc).__name__}: {exc}"
            log.info("audio capture could not open a device: %s", self._failure)
            self._stream = None
            return False

    def stop(self) -> None:
        """Stop capturing and close the device."""
        if not self._running:
            return

        self._stop_event.set()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None

        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass
            self._stream = None

        self._running = False

    def _capture_loop(self) -> None:
        """Read chunks until asked to stop; drop rather than block when full."""
        while not self._stop_event.is_set():
            try:
                if self._stream is None or not self._stream.is_active():
                    break
                data = self._stream.read(
                    self.config.chunk_size, exception_on_overflow=False
                )
            except Exception as exc:  # noqa: BLE001 - a dead device ends capture
                log.debug("audio capture loop ended: %s", exc)
                break
            try:
                self._queue.put_nowait(np.frombuffer(data, dtype=np.int16))
            except Full:
                continue

    def read(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """Return the next chunk, or ``None`` when nothing arrives in time."""
        if not self._running:
            return None
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return None

    def clear_buffer(self) -> None:
        """Discard whatever is queued."""
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                return

    def close(self) -> None:
        """Stop capturing and release the PyAudio context."""
        self.stop()
        if self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass
            self._pyaudio = None
