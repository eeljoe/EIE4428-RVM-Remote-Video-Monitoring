"""Objective quality metrics: PSNR and SSIM.

Reporting a number is the only way to say *how much* a codec setting cost in
quality, and the rate control loop needs that feedback: QP is chosen from the
buffer, but the report and the live dashboard need to show the distortion the
choice actually produced.

PSNR is the classical metric and is what the course uses as the objective in
"minimise distortion subject to a maximum rate".  It is a pure full-signal
fidelity measure, which means it is comparatively insensitive to structural
changes -- a blurred picture can still score respectably.

SSIM complements it by comparing local luminance, contrast and structure, so it
drops sharply when spatial detail is destroyed, which is exactly the failure
mode of an over-coarsened quantiser.
"""

from __future__ import annotations

import numpy as np

__all__ = ["BLOCK_SIZE", "mse", "psnr", "ssim"]

BLOCK_SIZE = 8
_PEAK = 255.0

# SSIM stabilising constants for 8-bit imagery.
_C1 = (0.01 * _PEAK) ** 2
_C2 = (0.03 * _PEAK) ** 2


def _as_luma_pair(
    reference: np.ndarray, distorted: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    reference = _to_luma(reference)
    distorted = _to_luma(distorted)

    if reference.shape != distorted.shape:
        raise ValueError(
            f"frame shapes disagree: {reference.shape} vs {distorted.shape}"
        )

    return reference.astype(np.float64), distorted.astype(np.float64)


def _to_luma(image: np.ndarray) -> np.ndarray:
    """Reduce an image to its luma plane.

    Accepts a single plane directly, or an ``(H, W, 3)`` colour image which is
    converted with the CCIR-601 weights.  Measuring on luma matches how the
    metrics are defined and avoids scoring a picture three times over on
    channels that carry mostly the same structure.
    """
    image = np.asarray(image)
    if image.ndim == 2:
        return image
    if image.ndim == 3 and image.shape[2] == 3:
        source = image.astype(np.float64)
        return (
            0.299 * source[..., 0] + 0.587 * source[..., 1] + 0.114 * source[..., 2]
        )
    raise ValueError(
        f"expected a single plane or an (H, W, 3) image, got shape {image.shape}"
    )


def mse(reference: np.ndarray, distorted: np.ndarray) -> float:
    """Mean squared error between two luma planes."""
    left, right = _as_luma_pair(reference, distorted)
    return float(np.mean((left - right) ** 2))


def psnr(reference: np.ndarray, distorted: np.ndarray) -> float:
    """Peak signal-to-noise ratio in dB, with ``MAX = 255``.

    Returns ``inf`` for identical planes.  The relation is
    ``PSNR = 10 log10(MAX^2 / MSE)``, so halving the MSE buys about 3 dB.
    """
    error = mse(reference, distorted)
    if error <= 0:
        return float("inf")
    return float(10.0 * np.log10((_PEAK**2) / error))


def _blocks(plane: np.ndarray) -> np.ndarray:
    """Reshape a plane into non-overlapping ``(rows, cols, 8, 8)`` blocks."""
    rows = plane.shape[0] // BLOCK_SIZE * BLOCK_SIZE
    columns = plane.shape[1] // BLOCK_SIZE * BLOCK_SIZE
    aligned = plane[:rows, :columns]
    return aligned.reshape(
        rows // BLOCK_SIZE, BLOCK_SIZE, columns // BLOCK_SIZE, BLOCK_SIZE
    ).transpose(0, 2, 1, 3)


def ssim(reference: np.ndarray, distorted: np.ndarray) -> float:
    """Mean structural similarity over non-overlapping 8x8 windows.

    Each window contributes::

        (2 mu_x mu_y + C1)(2 sigma_xy + C2)
        ------------------------------------------
        (mu_x^2 + mu_y^2 + C1)(sigma_x^2 + sigma_y^2 + C2)

    Any remainder at the right and bottom edges is ignored, so partial blocks
    never bias the average.
    """
    left, right = _as_luma_pair(reference, distorted)

    a = _blocks(left)
    b = _blocks(right)

    mu_x = a.mean(axis=(2, 3))
    mu_y = b.mean(axis=(2, 3))

    mu_x_squared = mu_x**2
    mu_y_squared = mu_y**2
    mu_xy = mu_x * mu_y

    sigma_x = a.var(axis=(2, 3))
    sigma_y = b.var(axis=(2, 3))
    sigma_xy = ((a - mu_x[..., None, None]) * (b - mu_y[..., None, None])).mean(
        axis=(2, 3)
    )

    luminance = (2 * mu_xy + _C1) / (mu_x_squared + mu_y_squared + _C1)
    structure = (2 * sigma_xy + _C2) / (sigma_x + sigma_y + _C2)

    return float(np.mean(luminance * structure))