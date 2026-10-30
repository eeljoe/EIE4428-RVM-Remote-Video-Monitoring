"""Object tracking: giving moving things an identity across frames.

The motion detector reports that *something* moved and draws one box around
all of it.  An operator watching for the brief's "object tracking" feature
needs the next step: which distinct objects moved, where each one went, and
whether the thing in the corner now is the same thing that crossed the room a
second ago.

Two classical stages, no learned models -- same reasoning as the detectors in
:mod:`rvm.analysis.detect`:

* **Connected components.**  Adjacent changed pixels belong to the same
  object, so the mask is split into one bounding box per blob.  Implemented
  with row-run union-find in pure NumPy so the module carries no hard OpenCV
  dependency.
* **Nearest-centroid association.**  Between consecutive frames a real object
  moves only a few pixels, so each known track claims the closest detection
  within a fixed radius.  Unmatched detections start new tracks; unmatched
  tracks coast for a few frames through brief occlusion before expiring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

__all__ = ["CentroidTracker", "Track", "regions_from_mask"]


def regions_from_mask(mask: np.ndarray, min_area: int = 16) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of the connected changed regions in a binary mask.

    Connectivity is eight-way: a fast edge often leaves diagonal trails, and
    splitting those into separate objects would double-count one mover.
    Returns ``(top, left, bottom, right)`` boxes -- the same convention
    :class:`~rvm.analysis.detect.MotionResult` uses -- in scan order.
    """
    mask = np.asarray(mask)
    if mask.ndim != 2:
        raise ValueError(f"expected a 2-D mask, got shape {mask.shape}")

    parent: list[int] = []
    runs: list[tuple[int, int, int, int]] = []  # (row, start, end, label)

    def find(label: int) -> int:
        while parent[label] != label:
            parent[label] = parent[parent[label]]
            label = parent[label]
        return label

    def union(a: int, b: int) -> int:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
        return find(a)

    previous: list[tuple[int, int, int]] = []  # (start, end, label)
    for row_index, row in enumerate(mask):
        nonzero = np.flatnonzero(row)
        current: list[tuple[int, int, int]] = []
        if nonzero.size:
            splits = np.flatnonzero(np.diff(nonzero) > 1)
            edges = np.concatenate(([0], splits + 1, [nonzero.size]))
            for start_idx, end_idx in zip(edges[:-1], edges[1:]):
                start, end = int(nonzero[start_idx]), int(nonzero[end_idx - 1])
                label = len(parent)
                parent.append(label)
                for prev_start, prev_end, prev_label in previous:
                    # One column of slack on each side covers the diagonals.
                    if start <= prev_end + 1 and end + 1 >= prev_start:
                        label = union(label, prev_label)
                current.append((start, end, label))
                runs.append((row_index, start, end, label))
        previous = current

    boxes: dict[int, list[int]] = {}  # root -> [top, left, bottom, right, area]
    for row_index, start, end, label in runs:
        box = boxes.setdefault(find(label), [row_index, start, row_index, end, 0])
        box[1] = min(box[1], start)
        box[2] = row_index
        box[3] = max(box[3], end)
        box[4] += end - start + 1

    regions = [
        (top, left, bottom + 1, right + 1)
        for top, left, bottom, right, area in boxes.values()
        if area >= min_area
    ]
    regions.sort()
    return regions


def _centre(box: tuple[int, int, int, int]) -> tuple[float, float]:
    """The ``(row, column)`` centre of a ``(top, left, bottom, right)`` box."""
    top, left, bottom, right = box
    return (top + bottom) / 2.0, (left + right) / 2.0


@dataclass
class Track:
    """One object followed across frames, in ``(top, left, bottom, right)`` boxes."""

    id: int
    bbox: tuple[int, int, int, int]
    centroid: tuple[float, float]  # (row, column), pixel units
    trail: list[tuple[float, float]] = field(default_factory=list)
    frames: int = 1
    missed: int = 0

    def snapshot(self) -> dict:
        """JSON-friendly view; points are emitted as ``[x, y]`` pixel pairs."""
        return {
            "id": self.id,
            "bbox": [int(v) for v in self.bbox],
            "centroid": [self.centroid[1], self.centroid[0]],
            "trail": [[x, y] for y, x in self.trail],
            "frames": self.frames,
        }


class CentroidTracker:
    """Nearest-centroid association of detection boxes across frames.

    ``max_distance`` is the furthest a box centre may move between frames and
    still count as the same object -- beyond it, the detection starts a new
    track.  ``max_missed`` is how many consecutive frames a track may go
    unseen before expiring, which carries an identity through brief
    occlusions.  ``trail_length`` bounds how much history each track draws.
    """

    def __init__(
        self,
        max_distance: float = 48.0,
        max_missed: int = 5,
        trail_length: int = 12,
    ) -> None:
        if max_distance <= 0:
            raise ValueError(f"max_distance must be positive, got {max_distance}")
        if max_missed < 0:
            raise ValueError(f"max_missed must be >= 0, got {max_missed}")
        if trail_length <= 0:
            raise ValueError(f"trail_length must be positive, got {trail_length}")

        self.max_distance = max_distance
        self.max_missed = max_missed
        self.trail_length = trail_length
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    def update(self, boxes) -> list[Track]:
        """Match detection ``boxes`` to tracks; return the ones seen now."""
        detections = [(_centre(box), box) for box in boxes]
        unmatched = set(range(len(detections)))

        for track in self._tracks.values():
            best_index, best_distance = None, self.max_distance
            for index in unmatched:
                row, column = detections[index][0]
                distance = math.hypot(
                    track.centroid[0] - row, track.centroid[1] - column
                )
                if distance <= best_distance:
                    best_index, best_distance = index, distance

            if best_index is None:
                track.missed += 1
            else:
                track.centroid, track.bbox = detections[best_index]
                track.frames += 1
                track.missed = 0
                track.trail.append(track.centroid)
                del track.trail[: -self.trail_length]
                unmatched.discard(best_index)

        for index in unmatched:
            centroid, box = detections[index]
            self._tracks[self._next_id] = Track(
                id=self._next_id,
                bbox=box,
                centroid=centroid,
                trail=[centroid],
            )
            self._next_id += 1

        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if track.missed > self.max_missed
        ]
        for track_id in expired:
            del self._tracks[track_id]

        return [track for track in self._tracks.values() if track.missed == 0]

    def reset(self) -> None:
        """Forget every track; the next frame starts numbering from one."""
        self._tracks.clear()
        self._next_id = 1
