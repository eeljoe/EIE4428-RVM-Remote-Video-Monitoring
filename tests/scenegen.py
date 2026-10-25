"""Synthetic scene generation shared by the codec and analysis tests.

Real camera imagery has structure -- smooth shading gradients, edges, objects
with texture.  Pure random noise does not, and white noise is a pathological
input for any motion estimator: its sum-of-absolute-differences surface is a
narrow spike at the true offset surrounded by a flat noise floor, so no
hill-climbing search can find it.  The scenes here reproduce the structure a
monitoring camera actually sees, which keeps the motion and rate-control tests
meaningful.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "moving_scene",
    "static_scene",
    "structured_shift_scene",
]


def _canvas(width: int, height: int, seed: int, margin: int = 32) -> np.ndarray:
    """Build a textured canvas with smooth shading plus rectangular objects."""
    rng = np.random.default_rng(seed)
    canvas_height = height + 2 * margin
    canvas_width = width + 2 * margin

    rows, columns = np.mgrid[0:canvas_height, 0:canvas_width].astype(np.float32)
    canvas = (
        40.0
        + 100.0 * np.sin(columns / 25.0)
        + 60.0 * np.cos(rows / 17.0)
        + 40.0 * np.sin((columns + rows) / 41.0)
    )

    for _ in range(6):
        top = int(rng.integers(0, canvas_height - 24))
        left = int(rng.integers(0, canvas_width - 32))
        canvas[top : top + 24, left : left + 32] += rng.uniform(-70.0, 70.0)

    return canvas.astype(np.float32), margin


def structured_shift_scene(
    width: int = 64,
    height: int = 64,
    dx: int = 0,
    dy: int = 0,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(current, previous)`` with true motion vector ``previous -> current``."""
    canvas, margin = _canvas(width, height, seed)
    previous = canvas[margin : margin + height, margin : margin + width]
    current = canvas[
        margin - dy : margin - dy + height, margin - dx : margin - dx + width
    ]
    return current.copy(), previous.copy()


def moving_scene(
    frame_index: int,
    width: int = 64,
    height: int = 64,
    dx: int = 2,
    dy: int = -1,
    seed: int = 0,
    object_size: int = 16,
) -> np.ndarray:
    """A frame from a sequence where one bright square moves by ``(dx, dy)`` per step.

    The background is stationary, so every block outside the object has a true
    motion vector of zero -- which is exactly the situation the monitoring
    motion detector has to recognise.
    """
    canvas, margin = _canvas(width, height, seed)
    frame = canvas[margin : margin + height, margin : margin + width].copy()

    span_x = width + object_size * 4
    span_y = height + object_size * 4
    left = max(0, min(margin + object_size + dx * frame_index, width - object_size))
    top = max(0, min(margin + object_size + dy * frame_index, height - object_size))
    left = min(left, span_x - object_size)
    top = min(top, span_y - object_size)

    ramp = np.arange(object_size, dtype=np.float32)
    pattern = 200.0 + 30.0 * np.cos(ramp[None, :] / 3.0) * np.cos(ramp[:, None] / 5.0)
    frame[top : top + object_size, left : left + object_size] = pattern

    return frame


def static_scene(
    width: int = 64, height: int = 64, seed: int = 0
) -> np.ndarray:
    """A single stationary frame."""
    return moving_scene(0, width=width, height=height, dx=0, dy=0, seed=seed)