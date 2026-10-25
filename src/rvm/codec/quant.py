"""Quality-scaled scalar quantisation of DCT coefficients.

Quantisation is where the bitrate is actually spent.  Dividing by a step size
and rounding throws away the resolution the step size cannot justify; the
reconstruction error is bounded by half a step, so a larger step means a larger
distortion for every coefficient.  This is the single most important lever in
the encoder, because

    QP up  =>  bit rate down  =>  distortion up

which is the trade-off the course calls the rate-distortion problem.

Two pieces of knowledge are encoded here:

* a **base quantisation matrix** whose entries follow the human contrast
  sensitivity function -- small steps at low spatial frequencies where the eye
  is sharp, large steps at high frequencies where it is not;
* a **quality-to-QP mapping** following the H.264 convention that a QP step of 6
  approximately doubles the step size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dct import BLOCK_SIZE

__all__ = [
    "LUMA_QUANT_MATRIX",
    "CHROMA_QUANT_MATRIX",
    "QUANT_MIN",
    "QUANT_MAX",
    "QP_MIN",
    "QP_MAX",
    "QuantParams",
    "build_quant_table",
    "clip_quant_table",
    "dequantize_block",
    "quality_to_qp",
    "quality_to_qscale",
    "quantize_block",
]

# Legal step sizes.  The domain is a 16-bit level space: the coarsest setting
# must be able to zero out every coefficient (a step >= the largest possible DC
# value of 8 * 255), otherwise low quality settings saturate and stop shrinking
# the bitrate.
QUANT_MIN = 1
QUANT_MAX = 32767

# H.264 quantiser parameter range.
QP_MIN = 1
QP_MAX = 51

# Base luma matrix in raster order.  Small at the top-left (low frequency, high
# visual weight) and growing towards the bottom-right (high frequency).
LUMA_QUANT_MATRIX = np.array(
    [
        [16, 11, 10, 16, 24, 40, 51, 61],
        [12, 12, 14, 19, 26, 58, 60, 55],
        [14, 13, 16, 24, 40, 57, 69, 56],
        [14, 17, 22, 29, 51, 87, 80, 62],
        [18, 22, 37, 56, 68, 109, 103, 77],
        [24, 35, 55, 64, 81, 104, 113, 92],
        [49, 64, 78, 87, 103, 121, 120, 101],
        [72, 92, 95, 98, 112, 100, 103, 99],
    ],
    dtype=np.int32,
)

# Chrominance is perceptually less important, so it starts from a coarser base.
CHROMA_QUANT_MATRIX = np.array(
    [
        [17, 18, 24, 47, 99, 99, 99, 99],
        [18, 21, 26, 66, 99, 99, 99, 99],
        [24, 26, 56, 99, 99, 99, 99, 99],
        [47, 66, 99, 99, 99, 99, 99, 99],
        [99, 99, 99, 99, 99, 99, 99, 99],
        [99, 99, 99, 99, 99, 99, 99, 99],
        [99, 99, 99, 99, 99, 99, 99, 99],
        [99, 99, 99, 99, 99, 99, 99, 99],
    ],
    dtype=np.int32,
)


def quality_to_qp(quality: float) -> int:
    """Map a 1-100 quality setting onto an H.264-style QP in ``[1, 51]``.

    The mapping is linear and inverted: quality 100 is the finest quantiser
    (QP 1) and quality 1 the coarsest (QP 51).
    """
    quality = min(100.0, max(1.0, float(quality)))
    span = QP_MAX - QP_MIN
    qp = QP_MIN + (100.0 - quality) / 99.0 * span
    return int(min(QP_MAX, max(QP_MIN, round(qp))))


def quality_to_qscale(quality: float) -> float:
    """Return the step-size multiplier for a 1-100 quality setting.

    Follows the H.264 rule of thumb that six QP steps double the step size, so
    ``qscale = 2 ** ((qp - 1) / 6)``.  Quality 100 is the identity transform.
    """
    return float(2.0 ** ((quality_to_qp(quality) - 1) / 6.0))


def clip_quant_table(table: np.ndarray) -> np.ndarray:
    """Clamp a quantisation matrix into the legal step-size range."""
    return np.clip(table, QUANT_MIN, QUANT_MAX).astype(np.int32)


def build_quant_table(
    quality: float, base: np.ndarray | None = None
) -> np.ndarray:
    """Scale a base quantisation matrix to a 1-100 quality setting."""
    matrix = LUMA_QUANT_MATRIX if base is None else base
    scale = quality_to_qscale(quality)
    return clip_quant_table(np.rint(matrix.astype(np.float64) * scale))


def quantize_block(coefficients: np.ndarray, table: np.ndarray) -> np.ndarray:
    """Divide by the step size and round to integer quantisation levels."""
    if coefficients.shape[-2:] != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(
            f"expected (..., 8, 8) coefficients, got shape {coefficients.shape}"
        )
    steps = table.astype(np.float64)
    return np.rint(coefficients.astype(np.float64) / steps).astype(np.int32)


def dequantize_block(levels: np.ndarray, table: np.ndarray) -> np.ndarray:
    """Multiply integer levels back by the step size to recover estimates."""
    if levels.shape[-2:] != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(
            f"expected (..., 8, 8) levels, got shape {levels.shape}"
        )
    return levels.astype(np.float64) * table.astype(np.float64)


@dataclass(frozen=True)
class QuantParams:
    """The quantiser state for one frame, as chosen by rate control."""

    quality: float = 75.0
    qp: int | None = None
    min_qp: int = QP_MIN
    max_qp: int = QP_MAX

    def __post_init__(self) -> None:
        if self.min_qp > self.max_qp:
            raise ValueError(f"empty QP window: {self.min_qp} > {self.max_qp}")

        if self.qp is None:
            resolved = quality_to_qp(self.quality)
        else:
            resolved = int(self.qp)

        windowed = min(self.max_qp, max(self.min_qp, resolved))
        object.__setattr__(self, "qp", windowed)

    @property
    def qscale(self) -> float:
        """Step-size multiplier implied by the resolved QP."""
        return float(2.0 ** ((self.qp - 1) / 6.0))

    def luma_table(self) -> np.ndarray:
        return build_quant_table_from_qscale(LUMA_QUANT_MATRIX, self.qscale)

    def chroma_table(self) -> np.ndarray:
        return build_quant_table_from_qscale(CHROMA_QUANT_MATRIX, self.qscale)


def build_quant_table_from_qscale(base: np.ndarray, qscale: float) -> np.ndarray:
    """Scale a base matrix by an explicit multiplier."""
    return clip_quant_table(np.rint(base.astype(np.float64) * qscale))