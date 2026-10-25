"""Orthonormal 8x8 two-dimensional DCT and its inverse.

The DCT is the decorrelating step of the hybrid coder: it maps an 8x8 block of
spatially correlated pixels into 64 coefficients whose magnitudes decay with
spatial frequency, so that the quantiser can discard the high-frequency terms
where the eye is least sensitive.

The transform used here is the orthonormal DCT-II::

    C[u] = a(u) * sum_x  f[x] * cos((2x + 1) * u * pi / (2N))
    a(0) = sqrt(1/N),  a(u > 0) = sqrt(2/N)

Applied separably in both axes, which reduces the cost from :math:`O(N^4)` to
:math:`O(N^3)` and lets us factor the 2-D transform into two 1-D passes.  The
orthonormal convention keeps the transform energy-preserving, so rounding error
accumulates symmetrically on the way back -- and gives a clean DC relationship,
``DC = 8 * mean(block)``, which makes the rate-control maths easy to reason about.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "BLOCK_SIZE",
    "dct2d",
    "dct2d_blocks",
    "idct2d",
    "idct2d_blocks",
]

BLOCK_SIZE = 8


def _build_basis() -> np.ndarray:
    """Precompute the orthonormal 1-D DCT-II basis matrix ``C[u, x]``."""
    n = BLOCK_SIZE
    u = np.arange(n).reshape(-1, 1)
    x = np.arange(n).reshape(1, -1)

    basis = np.cos((2.0 * x + 1.0) * u * np.pi / (2.0 * n))

    # Scale row 0 by sqrt(1/N) and the rest by sqrt(2/N).
    basis *= np.sqrt(2.0 / n)
    basis[0] /= np.sqrt(2.0)

    return basis


_BASIS = _build_basis()


def _as_block(array: np.ndarray, name: str) -> np.ndarray:
    if array.shape != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(
            f"{name} must be {BLOCK_SIZE}x{BLOCK_SIZE}, got {array.shape}"
        )
    return array.astype(np.float64, copy=False)


def dct2d(block: np.ndarray) -> np.ndarray:
    """Forward 2-D DCT of a single 8x8 block."""
    data = _as_block(block, "block")
    return _BASIS @ data @ _BASIS.T


def idct2d(coefficients: np.ndarray) -> np.ndarray:
    """Inverse 2-D DCT of a single 8x8 coefficient block."""
    data = _as_block(coefficients, "coefficients")
    return _BASIS.T @ data @ _BASIS


def dct2d_blocks(blocks: np.ndarray) -> np.ndarray:
    """Forward 2-D DCT of a stack ``(N, 8, 8)`` of blocks."""
    if blocks.ndim != 3 or blocks.shape[1:] != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(f"expected (N, 8, 8) blocks, got shape {blocks.shape}")
    return np.matmul(np.matmul(_BASIS, blocks.astype(np.float64, copy=False)), _BASIS.T)


def idct2d_blocks(coefficients: np.ndarray) -> np.ndarray:
    """Inverse 2-D DCT of a stack ``(N, 8, 8)`` of coefficient blocks."""
    if coefficients.ndim != 3 or coefficients.shape[1:] != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(
            f"expected (N, 8, 8) coefficient blocks, got shape {coefficients.shape}"
        )
    return np.matmul(np.matmul(_BASIS.T, coefficients.astype(np.float64, copy=False)), _BASIS)