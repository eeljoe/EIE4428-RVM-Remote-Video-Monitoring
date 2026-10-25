"""RGB <-> YCbCr conversion and chroma sub-sampling.

The monitor-ready RGB triplet is a poor candidate for compression: all three
components carry roughly the same amount of information and any two of them
determine the third.  CCIR-601 therefore separates *luma* from *chroma*::

    Y  =  0.299R + 0.587G + 0.114B
    Cb = 128 - 0.168736R - 0.331264G + 0.500000B
    Cr = 128 + 0.500000R - 0.418688G - 0.081312B

With ``R = G = B`` we get ``Y = R`` and ``Cb = Cr = 128``: grey input carries no
chroma at all.  Since human vision is far less sensitive to colour detail than
to luminance detail, the chroma planes can be sampled less densely.  4:2:0
keeps full luma resolution but quarters each chroma plane, which turns 24
bits/pixel of RGB into 12 bits/pixel.

Everything here uses the "full range" JPEG convention: ``Y`` lives in
``[0, 255]`` and ``Cb``/``Cr`` live in ``[0, 255]`` with 128 as neutral.
"""

from __future__ import annotations

from enum import Enum

import numpy as np

__all__ = [
    "ChromaSubsampling",
    "from_planes",
    "rgb_to_ycbcr",
    "subsample_420",
    "to_planes",
    "upsample_420",
    "ycbcr_to_rgb",
]


# CCIR-601 luma weights (sum to 1.0).
_KR, _KG, _KB = 0.299, 0.587, 0.114

# Derived from the luma weights via
#   Cb = 128 + (B - Y) / 1.772
#   Cr = 128 + (R - Y) / 1.402
_KCB_B = 0.5                                       # 0.500000
_KCB_R = -_KR / (2.0 * (1.0 - _KB))               # -0.168736
_KCB_G = -_KG / (2.0 * (1.0 - _KB))               # -0.331264
_KCR_R = 0.5                                       # 0.500000
_KCR_G = -_KG / (2.0 * (1.0 - _KR))               # -0.418688
_KCR_B = -_KB / (2.0 * (1.0 - _KR))               # -0.081312


class ChromaSubsampling(Enum):
    """Horizontal:vertical sampling factors applied to each colour plane.

    The ``label`` is the conventional J:a:b notation.  In ``4:2:0`` the luma
    plane is sampled at :math:`J = 4` samples per 4-pixel row (vertical
    reference ``b = 2``), while each chroma plane carries ``a = 2`` samples
    that repeat over ``b = 2`` rows -- i.e. chroma is halved both ways.
    """

    FOUR_FOUR_FOUR = ((1, 1), (1, 1), (1, 1))
    FOUR_TWO_TWO = ((2, 1), (2, 1), (1, 1))
    FOUR_TWO_ZERO = ((2, 2), (1, 1), (1, 1))

    @property
    def label(self) -> str:
        return _SUBSAMPLING_LABELS[self]

    def sample_rates(self) -> tuple[int, ...]:
        """Vertical sampling factors of (Y, Cb, Cr), relative to the luma plane."""
        return tuple(v for _, v in self.value)


_SUBSAMPLING_LABELS = {
    ChromaSubsampling.FOUR_FOUR_FOUR: "4:4:4",
    ChromaSubsampling.FOUR_TWO_TWO: "4:2:2",
    ChromaSubsampling.FOUR_TWO_ZERO: "4:2:0",
}


def rgb_to_ycbcr(rgb: np.ndarray) -> np.ndarray:
    """Convert an ``(H, W, 3)`` uint8 RGB image to float32 YCbCr.

    Returns ``(H, W, 3)`` float32 with Y in ``[0, 255]`` and Cb/Cr in ``[0, 255]``.
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) RGB image, got shape {rgb.shape}")

    src = rgb.astype(np.float32)
    r, g, b = src[..., 0], src[..., 1], src[..., 2]

    y = _KR * r + _KG * g + _KB * b
    cb = 128.0 + _KCB_R * r + _KCB_G * g + _KCB_B * b
    cr = 128.0 + _KCR_R * r + _KCR_G * g + _KCR_B * b

    return np.stack((y, cb, cr), axis=-1).astype(np.float32)


def ycbcr_to_rgb(ycbcr: np.ndarray) -> np.ndarray:
    """Inverse of :func:`rgb_to_ycbcr`, returning an ``(H, W, 3)`` uint8 image."""
    if ycbcr.ndim != 3 or ycbcr.shape[2] != 3:
        raise ValueError(f"expected an (H, W, 3) YCbCr image, got shape {ycbcr.shape}")

    src = ycbcr.astype(np.float32)
    y, cb, cr = src[..., 0], src[..., 1] - 128.0, src[..., 2] - 128.0

    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb

    return np.clip(np.stack((r, g, b), axis=-1), 0, 255).astype(np.uint8)


def to_planes(ycbcr: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split an ``(H, W, 3)`` YCbCr image into three ``(H, W)`` float32 planes."""
    y, cb, cr = (np.ascontiguousarray(ycbcr[..., i]) for i in range(3))
    return y, cb, cr


def from_planes(
    y: np.ndarray, cb: np.ndarray, cr: np.ndarray
) -> np.ndarray:
    """Recombine three planes back into an ``(H, W, 3)`` YCbCr image."""
    if not (y.shape == cb.shape == cr.shape):
        raise ValueError(
            f"plane shapes disagree: {y.shape}, {cb.shape}, {cr.shape}"
        )
    return np.stack((y, cb, cr), axis=-1).astype(np.float32)


def subsample_420(plane: np.ndarray) -> np.ndarray:
    """Down-sample a plane by averaging each 2x2 group (4:2:0 chroma reduction).

    Averaging -- rather than point sampling -- suppresses aliasing that would
    otherwise show up as colour fringing once the plane is expanded again.
    """
    if plane.ndim != 2:
        raise ValueError(f"expected a 2-D plane, got shape {plane.shape}")

    height, width = plane.shape
    if height % 2 or width % 2:
        raise ValueError(
            f"4:2:0 sub-sampling needs even dimensions, got {height}x{width}"
        )

    src = plane.astype(np.float32)
    averaged = src.reshape(height // 2, 2, width // 2, 2).mean(axis=(1, 3))
    return averaged.astype(np.float32)


def upsample_420(plane: np.ndarray) -> np.ndarray:
    """Expand a 4:2:0 plane back to full resolution by pixel replication.

    Replication keeps each 2x2 output group identical, which is the simple
    "practical" up-sampling that MPEG-1/2 decoders use.
    """
    if plane.ndim != 2:
        raise ValueError(f"expected a 2-D plane, got shape {plane.shape}")

    height, width = plane.shape
    src = plane.astype(np.float32)
    return np.repeat(np.repeat(src, 2, axis=0), 2, axis=1)