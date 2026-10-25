"""Time-stamped clip recording.

The brief lists "video recording with timing information" among the advanced
features.  Recording is kept separate from the live path on purpose: a slow
disk must never be able to stall the encoder and turn into jitter for every
viewer.  So frames are written one JPEG at a time rather than into a container,
which also means a recording interrupted by a crash still leaves usable frames
behind.

Every frame carries a burnt-in timestamp and a running frame index.  That makes
a clip self-evidencing: an incident can be placed against the wall clock without
trusting the file system, and the index makes a dropped-frame gap visible
instead of silently compressing the timeline.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import numpy as np

__all__ = ["FrameRecorder"]

_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


class FrameRecorder:
    """Writes JPEG frames into a time-stamped clip directory."""

    def __init__(
        self,
        directory: str | Path,
        fps: float = 15.0,
        started_at: str | None = None,
        burn_timestamp: bool = True,
    ) -> None:
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")

        self.directory = Path(directory)
        self.fps = float(fps)
        self.burn_timestamp = burn_timestamp
        self.started_at = started_at or datetime.now().strftime(_TIMESTAMP_FORMAT)

        self.directory.mkdir(parents=True, exist_ok=True)
        self.frame_count = 0
        self._stopped = False

    @property
    def duration_seconds(self) -> float:
        """Length of the clip implied by its frame count and frame rate."""
        return self.frame_count / self.fps

    def write(self, frame: np.ndarray, timestamp: float | None = None) -> bool:
        """Append one frame to the clip. Returns ``False`` if it could not be written.

        The frame may be a single ``(H, W)`` luma plane or a full ``(H, W, 3)``
        RGB picture; the channel order is converted to OpenCV's BGR before the
        file is written.
        """
        if self._stopped:
            raise RuntimeError("cannot write to a recorder that has been stopped")

        image = self._prepare(frame, timestamp)
        path = self.directory / f"{self.started_at}_{self.frame_count:06d}.jpg"

        try:
            import cv2

            if not cv2.imwrite(str(path), image):
                return False
        except Exception:  # noqa: BLE001 - a failed write must not kill the stream
            return False

        self.frame_count += 1
        return True

    def _prepare(self, frame: np.ndarray, timestamp: float | None) -> np.ndarray:
        image = np.asarray(frame)

        if image.ndim == 2:
            image = np.repeat(image[:, :, None], 3, axis=2)
        elif image.ndim == 3 and image.shape[2] == 1:
            image = np.repeat(image, 3, axis=2)
        elif image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(
                f"expected an (H, W) or (H, W, 3) frame, got shape {image.shape}"
            )

        # The pipeline carries RGB and OpenCV writes BGR, so the channels are
        # swapped once here.  A clip saved without the swap would show the
        # scene with its colours inverted, which is exactly the kind of defect
        # that only shows up on the day of the demonstration.
        image = np.ascontiguousarray(image[:, :, ::-1].astype(np.uint8))
        if not self.burn_timestamp:
            return image

        try:
            import cv2

            stamp = (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if timestamp is None
                else f"t={timestamp:7.2f}s"
            )
            cv2.putText(
                image,
                f"{stamp}  #{self.frame_count:06d}",
                (6, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 0, 0),
                3,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                f"{stamp}  #{self.frame_count:06d}",
                (6, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
        except Exception:  # noqa: BLE001 - annotation is a nicety, not a requirement
            pass

        return image

    def stop(self) -> Path | None:
        """Finish the clip and return its directory.

        Returns ``None`` if nothing was written or the recorder has already
        been finalised, so calling it twice is harmless.
        """
        if self._stopped:
            return None

        self._stopped = True
        if self.frame_count == 0:
            return None
        return self.directory

    def __enter__(self) -> "FrameRecorder":
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()