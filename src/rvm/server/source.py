"""Frame sources for the video server.

Two sources implement the same small interface:

* :class:`CameraSource` reads a real webcam through OpenCV.
* :class:`SyntheticSource` generates a moving scene with a bright object
  crossing the view.

The synthetic source is not a toy.  A monitoring system has to be demonstrable
on any machine, including one with no webcam, in CI, and during a report
screenshot.  It also gives motion detection a known ground truth -- an object
that definitely is moving -- which a webcam cannot promise.
"""

from __future__ import annotations

import time

import numpy as np

__all__ = ["CameraSource", "CaptureSource", "SyntheticSource", "open_source"]


class CaptureSource:
    """Common interface for anything that yields RGB frames."""

    width: int
    height: int
    fps: float
    closed: bool = False

    def read(self) -> np.ndarray | None:
        raise NotImplementedError

    def close(self) -> None:
        self.closed = True


class CameraSource(CaptureSource):
    """A webcam, opened through OpenCV.

    Opening is deferred and failure is tolerated: a monitoring server that
    refuses to start because one camera is unplugged is less useful than one
    that reports the problem and carries on.
    """

    def __init__(self, index: int = 0, width: int = 640, height: int = 480, fps: float = 15.0):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self._capture = None
        self._open_error: str | None = None

    @property
    def available(self) -> bool:
        return self._capture is not None

    @property
    def open_error(self) -> str | None:
        return self._open_error

    @property
    def name(self) -> str:
        return f"camera:{self.index}"

    def open(self) -> bool:
        try:
            import cv2

            capture = cv2.VideoCapture(self.index)
            if not capture.isOpened():
                capture.release()
                self._open_error = f"camera index {self.index} could not be opened"
                return False

            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self._capture = capture
            self._open_error = None
            return True
        except Exception as exc:  # noqa: BLE001
            self._open_error = f"camera index {self.index} unavailable: {exc}"
            return False

    def read(self) -> np.ndarray | None:
        if self._capture is None and not self.open():
            return None

        grabbed, frame = self._capture.read()
        if not grabbed or frame is None:
            return None

        import cv2

        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height))
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self.closed = True


class SyntheticSource(CaptureSource):
    """A generated scene: smooth shading, a few blocks, and a moving object.

    The object crosses the view at a constant rate so the motion detector has
    something unambiguous to find.
    """

    def __init__(self, width: int = 640, height: int = 480, fps: float = 15.0, seed: int = 7):
        if width % 16 or height % 16:
            raise ValueError(
                f"{width}x{height} must be a multiple of 16 so the luma plane and "
                "the half-resolution chroma planes stay block aligned"
            )

        self.width = width
        self.height = height
        self.fps = fps
        self._index = 0
        self._last_read: float | None = None
        self._background = self._make_background(seed)

    @property
    def name(self) -> str:
        return "synthetic"

    def _make_background(self, seed: int) -> np.ndarray:
        rows, columns = np.mgrid[0 : self.height, 0 : self.width].astype(np.float64)
        luma = (
            45.0
            + 70.0 * np.sin(columns / 31.0)
            + 45.0 * np.cos(rows / 23.0)
            + 30.0 * np.sin((columns + rows) / 57.0)
        )

        rng = np.random.default_rng(seed)
        for _ in range(5):
            top = int(rng.integers(0, self.height - 40))
            left = int(rng.integers(0, self.width - 60))
            luma[top : top + 40, left : left + 60] += rng.uniform(-50.0, 50.0)

        return np.clip(luma, 0, 255)

    def read(self) -> np.ndarray:
        luma = self._background.copy()

        # The object sweeps left to right and wraps, so motion is continuous.
        object_size = max(16, min(self.width, self.height) // 5)
        span = self.width + object_size
        position = int((self._index * max(1, self.width // 40)) % span)
        left = max(0, min(position, self.width - object_size))
        top = self.height // 2 - object_size // 2

        ramp = np.arange(object_size, dtype=np.float64)
        luma[top : top + object_size, left : left + object_size] = (
            205.0 + 30.0 * np.cos(ramp[None, :] / 4.0) * np.cos(ramp[:, None] / 6.0)
        )

        self._index += 1
        self._pace(period_index=1)

        return self._to_rgb(luma)

    def _to_rgb(self, luma: np.ndarray) -> np.ndarray:
        """Turn the luma plane into a coloured scene.

        The hue varies across the view so that chroma carries real information.
        A grey scene would make the 4:2:0 reduction invisible in the output and
        would hide whether the chroma planes are being handled correctly.
        """
        rows, columns = np.mgrid[0 : self.height, 0 : self.width].astype(np.float64)

        gradient = np.clip(luma / 255.0, 0.0, 1.0)
        red = np.clip(255.0 * (0.25 + 0.70 * gradient) + 40.0 * np.sin(columns / 37.0), 0, 255)
        green = np.clip(255.0 * (0.20 + 0.75 * gradient) + 35.0 * np.cos(rows / 29.0), 0, 255)
        blue = np.clip(
            255.0 * (0.30 + 0.45 * (1.0 - gradient)) + 45.0 * np.sin((columns + rows) / 53.0),
            0,
            255,
        )
        return np.stack((red, green, blue), axis=-1).astype(np.uint8)

    def _pace(self, period_index: int = 1) -> float | None:
        """Sleep so the source emits pictures at roughly its declared rate."""
        if period_index <= 0:
            return None

        period = 1.0 / self.fps
        now = time.monotonic()
        if self._last_read is None:
            self._last_read = now
            return None

        elapsed = now - self._last_read
        remaining = period * period_index - elapsed
        if remaining > 0:
            time.sleep(remaining)
            self._last_read = time.monotonic()
        else:
            self._last_read = now
        return elapsed

    def close(self) -> None:
        self.closed = True


def open_source(
    prefer_camera: bool = True,
    camera_index: int = 0,
    width: int = 640,
    height: int = 480,
    fps: float = 15.0,
) -> CaptureSource:
    """Return a camera if one is usable, otherwise the synthetic generator."""
    if prefer_camera:
        camera = CameraSource(camera_index, width, height, fps)
        if camera.open():
            return camera
        camera.close()

    return SyntheticSource(width, height, fps)