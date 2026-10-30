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
