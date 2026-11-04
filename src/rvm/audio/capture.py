"""Microphone capture in a worker thread, with a bounded hand-off queue."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, RLock, Thread
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
        self._available: bool | None = None
        # Two threads constructing pyaudio.PyAudio() at once kills the process
        # with an access violation rather than raising, so the probe is
        # serialised and the result double-checked.  Reentrant because
        # available() holds it while _probe_device() calls _init_pyaudio(),
        # which takes it again.
        self._probe_lock = RLock()

    @property
    def available(self) -> bool:
        """Whether a microphone can actually be opened on this machine.

        Blocking on the first call (a PortAudio round trip, ~300 ms), so it must
        be called off the event loop.  Concurrent callers are serialised: two
        threads constructing ``pyaudio.PyAudio()`` at the same time crashes the
        process with an access violation, not an exception.
        """
        if self._available is None:
            with self._probe_lock:
                if self._available is None:
                    self._available = self._probe_device()
        return self._available

    @property
    def availability(self) -> bool | None:
        """What has been probed so far, without probing.

        For callers on the event loop: ``None`` means "nobody has looked yet",
        which is an answer, whereas calling :attr:`available` there would block
        and race the thread that is already looking.
        """
        return self._available

    def _probe_device(self) -> bool:
        if not self._init_pyaudio():
            return False
        try:
            self._pyaudio.get_default_input_device_info()
            return True
        except Exception as exc:  # noqa: BLE001 - no device is a normal state
            self._failure = f"{type(exc).__name__}: {exc}"
            log.info("no default input device: %s", self._failure)
            return False

    @property
    def unavailable_reason(self) -> str | None:
        if self._available is None:
            self.available
        return self._failure

    @property
    def running(self) -> bool:
        return self._running

    def _init_pyaudio(self) -> bool:
        if self._pyaudio is not None:
            return True
        if self._failure is not None:
            return False

        with self._probe_lock:
            if self._pyaudio is not None:
                return True
            try:
                import pyaudio

                self._pyaudio = pyaudio.PyAudio()
                return True
            except Exception as exc:  # noqa: BLE001 - missing module or no device
                self._failure = f"{type(exc).__name__}: {exc}"
                log.info("audio capture unavailable: %s", self._failure)
                return False

    def start(self) -> bool:
        """Open the device and begin capturing; returns whether it is running.

        The check is on the thread, not on the flag: a capture loop that died
        (device unplugged, driver reset) leaves no live thread, and a flag-only
        test would report "already running" and hand back a dead stream.
        """
        if self._running and self._capture_thread is not None and self._capture_thread.is_alive():
            return True
        if not self._probe_device():
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
            # Set the flag *before* the thread runs: the loop clears it in its
            # ``finally``, so a device that dies immediately would otherwise
            # clear it first and then have it set back to True by this line,
            # leaving "running" true with no thread behind it.
            self._running = True
            self._capture_thread.start()
            return True
        except Exception as exc:  # noqa: BLE001 - no default input device is normal
            self._failure = f"{type(exc).__name__}: {exc}"
            log.info("audio capture could not open a device: %s", self._failure)
            self._stream = None
            self._running = False
            return False


    def stop(self) -> None:
        """Stop capturing and release the device.

        No early return on ``not self._running``: a capture loop that died on
        its own leaves the flag False with the PortAudio stream still open, and
        returning there leaks one handle per unplugged device.  The join is
        skipped when the thread never started, which ``start()`` can be
        interrupted between.
        """
        self._stop_event.set()

        thread, self._capture_thread = self._capture_thread, None
        if thread is not None and thread.ident is not None:
            thread.join(timeout=2.0)

        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:  # noqa: BLE001 - closing is best effort
                pass

        self._running = False

    def _capture_loop(self) -> None:
        """Read chunks until asked to stop; drop rather than block when full.

        ``_running`` is cleared in ``finally``: every exit path here (stop
        requested, device died, read failed) leaves the flag truthful, so
        ``/api/audio/events`` cannot report a stream that no longer exists.
        """
        try:
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
        finally:
            self._running = False

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

