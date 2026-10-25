"""Motion estimation and motion compensation.

Video frames are not independent.  Successive frames of a scene are similar --
the course calls this *interframe* redundancy -- so most of the second frame can
be predicted from the first and only the difference has to be coded.  That
difference is the *residual*.

The predictor is a motion-compensated prediction: each block is copied from the
previous frame but offset by a motion vector ``(dx, dy)``, and the vector itself
has to be transmitted because the receiver cannot guess it.

Search strategy
---------------
A naive full search evaluates ``(2r+1)^2`` offsets for every block.  Measured on
this implementation that costs roughly 50 ms per frame at 320x240, which alone
would cap the encoder at about 20 fps before any other work happens.  So the
search is split into two stages:

1. A **global three-step search** finds the dominant motion of the whole frame.
   Each candidate is a single shifted-plane sum of absolute differences, which
   is a contiguous slice and therefore very cheap.
2. A **local refinement** scans a small window around that global vector, still
   evaluating every offset as a whole-frame operation but now keeping a running
   minimum *per block*.  This is what lets a static background sit at zero while
   a moving region gets its own vector.

The trick that makes stage 2 affordable is that every candidate offset is
measured from the reference frame origin rather than from each block's own
current position.  That keeps every evaluation a contiguous slice while still
producing a genuinely per-block motion field.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dct import BLOCK_SIZE

__all__ = [
    "BLOCK_SIZE",
    "MotionField",
    "block_shape",
    "compensate",
    "estimate_motion",
    "global_motion_search",
    "refine_motion_field",
    "shift_plane",
]


#: Rate-distortion weight for motion-vector mode decision, in sum-of-absolute-
#: differences units per bit.  A displacement is only worth coding when it saves
#: more prediction error than the extra bits it costs.
MOTION_LAMBDA = 8.0


def _vector_bits(delta: int) -> float:
    """Extra bits a displacement costs relative to the zero vector."""
    if delta == 0:
        return 0.0
    magnitude = abs(delta)
    # se() zig-zag maps onto ue(), whose length is 2*floor(log2(v+1)) + 1.
    mapped = 2 * magnitude
    return float((mapped + 1).bit_length() - 1)


@dataclass(frozen=True)
class MotionField:
    """Per-block motion vectors and their matching costs.

    ``dx``/``dy``/``cost`` are all ``(block_rows, block_cols)``.
    """

    dx: np.ndarray
    dy: np.ndarray
    cost: np.ndarray

    @property
    def block_shape(self) -> tuple[int, int]:
        return self.dx.shape

    def as_int8(self) -> tuple[np.ndarray, np.ndarray]:
        """Clamp vectors to the range an 8-bit motion field can carry."""
        limit = 127
        return (
            np.clip(self.dx, -limit, limit).astype(np.int8),
            np.clip(self.dy, -limit, limit).astype(np.int8),
        )


def block_shape(width: int, height: int) -> tuple[int, int]:
    """Return ``(block_cols, block_rows)`` for a frame of the given size."""
    if width < BLOCK_SIZE or height < BLOCK_SIZE:
        raise ValueError(
            f"frame {width}x{height} is smaller than one {BLOCK_SIZE}x{BLOCK_SIZE} block"
        )
    return width // BLOCK_SIZE, height // BLOCK_SIZE


def shift_plane(plane: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Translate a plane by ``(dx, dy)``, replicating the edge to fill borders.

    Sample ``(r, c)`` of the result is ``plane[r - dy, c - dx]``, so the vector
    has the same sign convention as the one carried in the bitstream.

    The border is filled by copying the edge row or column.  The obvious
    implementation pads the plane first with ``numpy.pad``, but that routine
    is an order of magnitude slower than plain slicing for the small offsets
    the search actually uses, and the search evaluates hundreds of offsets per
    picture.
    """
    source = np.asarray(plane, dtype=np.float64)
    height, width = source.shape

    # Shift along the columns first, then along the rows.  Each step is a
    # couple of contiguous copies, so the whole translation costs two array
    # writes instead of a general-purpose pad.
    columns = np.empty((height, width), dtype=np.float64)
    if dx == 0:
        columns[:] = source
    elif dx > 0:
        columns[:, :dx] = source[:, :1]
        columns[:, dx:] = source[:, : width - dx]
    else:
        step = -dx
        columns[:, : width - step] = source[:, step:]
        columns[:, width - step :] = source[:, width - 1 : width]

    result = np.empty((height, width), dtype=np.float64)
    if dy == 0:
        result[:] = columns
    elif dy > 0:
        result[:dy] = columns[:1]
        result[dy:] = columns[: height - dy]
    else:
        step = -dy
        result[: height - step] = columns[step:]
        result[height - step :] = columns[height - 1 : height]

    return result


def _sad(plane: np.ndarray, shifted: np.ndarray) -> float:
    return float(np.abs(plane - shifted).sum())


def _aligned_frame_width(width: int) -> int:
    return width // BLOCK_SIZE * BLOCK_SIZE


def _blocks(frame: np.ndarray) -> np.ndarray:
    """Align a frame to whole blocks and return it as ``(rows, cols, 8, 8)``."""
    height = _aligned_frame_width(frame.shape[0])
    width = _aligned_frame_width(frame.shape[1])
    return frame[:height, :width].reshape(
        height // BLOCK_SIZE, BLOCK_SIZE, width // BLOCK_SIZE, BLOCK_SIZE
    ).transpose(0, 2, 1, 3)


def _block_sad(
    reference: np.ndarray, shifted: np.ndarray
) -> np.ndarray:
    """Per-block SAD between two aligned ``(rows, cols, 8, 8)`` stacks."""
    return np.abs(reference - shifted).sum(axis=(2, 3)).reshape(-1)


def _block_sad_planes(
    reference: np.ndarray, shifted: np.ndarray, rows: int, columns: int
) -> np.ndarray:
    """Per-block SAD between two whole planes, in block order.

    The planes are reshaped rather than transposed into blocks: a transpose
    copies the entire plane, and the refinement stage evaluates two dozen
    candidate offsets per picture, so those copies dominated its cost.
    """
    height = rows * BLOCK_SIZE
    width = columns * BLOCK_SIZE
    left = reference[:height, :width].reshape(rows, BLOCK_SIZE, columns, BLOCK_SIZE)
    right = shifted[:height, :width].reshape(rows, BLOCK_SIZE, columns, BLOCK_SIZE)
    return np.abs(left - right).sum(axis=(1, 3)).reshape(-1)


def global_motion_search(
    reference: np.ndarray,
    current: np.ndarray,
    search_range: int = 8,
) -> tuple[int, int, float]:
    """Three-step search for the single best offset of the whole frame.

    Starts at zero with a step of ``search_range // 2``, evaluates the centre and
    its four axis neighbours, then halves the step until it reaches one.  That
    covers a ``2 * search_range`` span in about ``5 * log2(search_range)``
    evaluations instead of ``(2r + 1) ** 2``.
    """
    if reference.shape != current.shape:
        raise ValueError(
            f"frame shapes disagree: {reference.shape} vs {current.shape}"
        )
    if search_range < 1:
        raise ValueError(f"search_range must be positive, got {search_range}")

    best_x, best_y = 0, 0
    best_cost = _sad(current, reference)
    step = max(1, search_range // 2)

    while step >= 1:
        improved = False
        for delta_y, delta_x in ((0, step), (0, -step), (step, 0), (-step, 0)):
            candidate_x = best_x + delta_x
            candidate_y = best_y + delta_y
            if abs(candidate_x) > search_range or abs(candidate_y) > search_range:
                continue

            cost = _sad(current, shift_plane(reference, candidate_x, candidate_y))
            if cost < best_cost:
                best_cost, best_x, best_y = cost, candidate_x, candidate_y
                improved = True

        if not improved and step == 1:
            break
        step //= 2

    return best_x, best_y, best_cost


def refine_motion_field(
    reference: np.ndarray,
    current: np.ndarray,
    base_dx: int,
    base_dy: int,
    window: int = 2,
    lambda_rd: float = MOTION_LAMBDA,
) -> MotionField:
    """Per-block refinement of a global motion vector.

    Every offset in the window is evaluated as a whole-frame operation against
    the reference frame, and the running minimum is kept per block.  The result
    is a genuinely per-block motion field, not a replicated global vector.

    Selection is rate-distortion, not pure error.  A non-zero vector has to be
    transmitted, so it is only accepted when it beats the current best by more
    than the ``lambda_rd`` cost of those extra bits.  Without that term the
    search happily spends four bits per block to shave a few units of sum of
    absolute differences, which is a straight loss: quantising the resulting
    slightly larger residual costs more than the vector saved.
    """
    if reference.shape != current.shape:
        raise ValueError(
            f"frame shapes disagree: {reference.shape} vs {current.shape}"
        )

    current_plane = np.asarray(current, dtype=np.float64)
    columns, rows = block_shape(reference.shape[1], reference.shape[0])
    block_count = rows * columns

    best_dx = np.full(block_count, base_dx, dtype=np.int32)
    best_dy = np.full(block_count, base_dy, dtype=np.int32)
    best_cost = np.full(block_count, np.inf, dtype=np.float64)

    for delta_y in range(-window, window + 1):
        for delta_x in range(-window, window + 1):
            candidate_x = base_dx + delta_x
            candidate_y = base_dy + delta_y
            shifted = shift_plane(reference, candidate_x, candidate_y)
            costs = _block_sad_planes(current_plane, shifted, rows, columns)

            # Charge a non-zero displacement for the bits it will cost.
            extra_bits = _vector_bits(delta_x) + _vector_bits(delta_y)
            costs = costs + lambda_rd * extra_bits

            better = costs < best_cost
            best_cost = np.where(better, costs, best_cost)
            best_dx = np.where(better, candidate_x, best_dx)
            best_dy = np.where(better, candidate_y, best_dy)

    return MotionField(
        dx=best_dx.reshape(rows, columns),
        dy=best_dy.reshape(rows, columns),
        cost=best_cost.reshape(rows, columns),
    )


def estimate_motion(
    reference: np.ndarray,
    current: np.ndarray,
    search_range: int = 8,
    refine_window: int = 2,
) -> MotionField:
    """Estimate motion for every block: global search, then local refinement."""
    global_dx, global_dy, _ = global_motion_search(
        reference, current, search_range=search_range
    )
    return refine_motion_field(
        reference,
        current,
        base_dx=global_dx,
        base_dy=global_dy,
        window=refine_window,
    )


def compensate(reference: np.ndarray, field: MotionField) -> np.ndarray:
    """Build the motion-compensated prediction for the current frame."""
    reference = np.asarray(reference, dtype=np.float64)
    rows, columns = field.block_shape
    expected = (rows * BLOCK_SIZE, columns * BLOCK_SIZE)
    if (reference.shape[0], reference.shape[1]) != expected:
        raise ValueError(
            f"reference shape {reference.shape} does not match motion field shape "
            f"{field.block_shape}"
        )

    prediction = np.empty(expected, dtype=np.float64)

    # The field is read once into plain Python integers: indexing a NumPy
    # array per block costs more than the arithmetic that follows.
    dx = field.dx.tolist()
    dy = field.dy.tolist()

    # Cache shifted planes so a vector reused by many blocks is computed once.
    cache: dict[tuple[int, int], np.ndarray] = {}
    for row in range(rows):
        for col in range(columns):
            key = (dx[row][col], dy[row][col])
            plane = cache.get(key)
            if plane is None:
                plane = shift_plane(reference, key[0], key[1])
                cache[key] = plane

            prediction[
                row * BLOCK_SIZE : (row + 1) * BLOCK_SIZE,
                col * BLOCK_SIZE : (col + 1) * BLOCK_SIZE,
            ] = plane[
                row * BLOCK_SIZE : (row + 1) * BLOCK_SIZE,
                col * BLOCK_SIZE : (col + 1) * BLOCK_SIZE,
            ]

    return prediction