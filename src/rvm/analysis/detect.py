"""Monitoring intelligence: motion detection and face detection.

These are the "special features" the mini-project brief invites beyond plain
remote monitoring.  Both are classical computer-vision stages rather than
learned models, which keeps them explainable and fast enough to run on every
captured frame.

Motion detection
----------------
A monitoring camera looks at a background that is usually still, so the useful
signal is the *difference* from the background rather than the picture itself.
A single thresholded frame difference is not enough on its own: sensor noise and
a slowly drifting camera would hold the alarm on permanently.  So the detector
keeps a running background model that is updated only slowly, compares against
that, and applies two further pieces of standard practice:

* **Erosion**, which removes isolated speckles so a handful of noisy pixels
  cannot raise an alarm.
* **Hysteresis**, with separate raise and clear thresholds, so a scene sitting
  near the threshold does not make the alarm flap on and off -- the single most
  irritating failure mode for an alarm indicator.

Face detection
--------------
Uses the Haar cascade shipped with OpenCV.  It is optional: if the cascade data
is unavailable the detector reports zero faces rather than failing the stream,
because a monitoring system that stops because of a missing asset is worse than
one that reports no faces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["FaceDetection", "FaceDetector", "MotionDetector", "MotionResult"]

_ERODE_KERNEL = np.ones((3, 3), dtype=np.uint8)


def _erode(mask: np.ndarray) -> np.ndarray:
    """Shrink a binary mask by one pixel on each side.

    Implemented with shifted copies rather than an OpenCV call so the module
    has no hard dependency on OpenCV being present.
    """
    eroded = mask.copy()
    eroded[1:, :] &= mask[:-1, :]
    eroded[:-1, :] &= mask[1:, :]
    eroded[:, 1:] &= mask[:, :-1]
    eroded[:, :-1] &= mask[:, 1:]
    return eroded


@dataclass
class MotionResult:
    """Outcome of one motion-detection pass."""

    motion_ratio: float
    alarm: bool
    mask: np.ndarray
    bbox: tuple[int, int, int, int] | None
    changed_pixels: int

    def snapshot(self) -> dict:
        """JSON-friendly view for the live dashboard."""
        top, left, bottom, right = self.bbox if self.bbox else (0, 0, 0, 0)
        return {
            "motion_ratio": round(self.motion_ratio, 5),
            "alarm": bool(self.alarm),
            "changed_pixels": int(self.changed_pixels),
            "bbox": [int(top), int(left), int(bottom), int(right)],
        }


class MotionDetector:
    """Background-subtracting motion detector with hysteresis and erosion."""

    def __init__(
        self,
        threshold: float = 0.01,
        clear_threshold: float | None = None,
        adapt_rate: float = 0.02,
        sensitivity: float = 12.0,
        erode: bool = True,
    ) -> None:
        if not 0.0 < threshold < 1.0:
            raise ValueError(f"threshold must be in (0, 1), got {threshold}")
        if not 0.0 < adapt_rate <= 1.0:
            raise ValueError(f"adapt_rate must be in (0, 1], got {adapt_rate}")

        self.threshold = threshold
        # Clearing below a lower level than raising above is what stops the
        # alarm from chattering when the scene sits near the threshold.
        self.clear_threshold = (
            clear_threshold if clear_threshold is not None else threshold * 0.5
        )
        self.adapt_rate = adapt_rate
        self.sensitivity = sensitivity
        self.erode = erode

        self._background: np.ndarray | None = None
        self._alarm_active = False

    @property
    def alarm_active(self) -> bool:
        return self._alarm_active

    @property
    def has_background(self) -> bool:
        return self._background is not None

    def reset(self) -> None:
        self._background = None
        self._alarm_active = False

    def update(self, luma: np.ndarray) -> MotionResult:
        """Compare a luma frame against the background and update the model."""
        frame = self._validate(luma).astype(np.float64)

        if self._background is None:
            # The very first frame defines the scene; there is nothing to
            # compare it against yet, so it is learnt silently.
            self._background = frame
            zeros = np.zeros(frame.shape, dtype=np.uint8)
            return MotionResult(0.0, False, zeros, None, 0)

        difference = np.abs(frame - self._background)
        mask = (difference > self.sensitivity).astype(np.uint8)

        if self.erode:
            mask = _erode(mask)

        changed = int(mask.sum())
        ratio = changed / float(mask.size)

        if ratio >= self.threshold:
            self._alarm_active = True
        elif ratio <= self.clear_threshold:
            self._alarm_active = False

        # Only adapt where nothing is happening, so a person standing in view
        # is never slowly absorbed into the background.
        if not self._alarm_active:
            self._background += self.adapt_rate * (frame - self._background)

        rows = np.nonzero(mask.any(axis=1))[0]
        columns = np.nonzero(mask.any(axis=0))[0]
        bbox = None
        if rows.size and columns.size:
            bbox = (
                int(rows[0]),
                int(columns[0]),
                int(rows[-1]) + 1,
                int(columns[-1]) + 1,
            )

        return MotionResult(ratio, self._alarm_active, mask, bbox, changed)

    @staticmethod
    def _validate(luma: np.ndarray) -> np.ndarray:
        frame = np.asarray(luma)
        if frame.ndim != 2:
            raise ValueError(
                f"motion detection needs a single luma plane, got shape {frame.shape}"
            )
        if frame.dtype != np.uint8:
            raise ValueError(f"expected a uint8 luma plane, got {frame.dtype}")
        return frame


@dataclass
class FaceDetection:
    """Faces found in one frame, as ``(x, y, width, height)`` boxes."""

    faces: list[tuple[int, int, int, int]] = field(default_factory=list)
    detector_name: str = "none"

    @property
    def count(self) -> int:
        return len(self.faces)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "faces": [list(box) for box in self.faces],
            "detector": self.detector_name,
        }


class FaceDetector:
    """Haar-cascade face detector that degrades gracefully when unavailable."""

    def __init__(self, cascade: str = "haarcascade_frontalface_default.xml") -> None:
        self.cascade_name = cascade
        self._classifier = None
        self._load_failed = False

    @property
    def available(self) -> bool:
        return self._classifier is not None

    def _load(self):
        if self._classifier is not None or self._load_failed:
            return self._classifier

        try:
            import cv2

            path = cv2.data.haarcascades + self.cascade_name
            classifier = cv2.CascadeClassifier(path)
            if classifier.empty():
                self._load_failed = True
                return None
            self._classifier = classifier
        except Exception:  # noqa: BLE001 - any failure means "no faces available"
            self._load_failed = True

        return self._classifier

    def detect(self, luma: np.ndarray) -> FaceDetection:
        """Locate faces in a luma frame, returning an empty result on any problem."""
        frame = np.asarray(luma)
        if frame.ndim != 2:
            raise ValueError(
                f"face detection needs a single luma plane, got shape {frame.shape}"
            )

        classifier = self._load()
        if classifier is None:
            return FaceDetection([], "unavailable")

        # The cascade needs more room than an 8x8 block to produce anything.
        if min(frame.shape) < 24:
            return FaceDetection([], "too-small")

        try:
            import cv2

            rectangles = classifier.detectMultiScale(
                frame,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(24, 24),
            )
        except Exception:  # noqa: BLE001
            return FaceDetection([], "error")

        faces = [
            (int(x), int(y), int(w), int(h)) for (x, y, w, h) in rectangles
        ]
        return FaceDetection(faces, self.cascade_name)