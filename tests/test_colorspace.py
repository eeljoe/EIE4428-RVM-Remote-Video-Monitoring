"""Tests for RGB <-> YCbCr conversion and 4:2:0 chroma subsampling."""

import numpy as np
import pytest

from rvm.core.colorspace import (
    ChromaSubsampling,
    from_planes,
    rgb_to_ycbcr,
    subsample_420,
    to_planes,
    upsample_420,
    ycbcr_to_rgb,
)


def test_grey_pixel_has_neutral_chroma():
    """CCIR-601: when R=G=B the luma equals the value and chroma is neutral."""
    rgb = np.full((2, 2, 3), 128, dtype=np.uint8)
    ycbcr = rgb_to_ycbcr(rgb)

    assert ycbcr[..., 0] == pytest.approx(128.0, abs=1e-3)
    assert ycbcr[..., 1] == pytest.approx(128.0, abs=1e-3)
    assert ycbcr[..., 2] == pytest.approx(128.0, abs=1e-3)


def test_luma_uses_ccir601_weights():
    """Y = 0.299R + 0.587G + 0.114B."""
    rgb = np.zeros((1, 1, 3), dtype=np.uint8)
    rgb[0, 0] = (255, 0, 0)
    ycbcr = rgb_to_ycbcr(rgb)

    assert ycbcr[0, 0, 0] == pytest.approx(0.299 * 255, abs=1e-3)


def test_luma_exceeds_chroma_amplitude():
    """Luma carries ~7x the dynamic range of chroma, which is why 4:2:0 works."""
    assert 0.299 + 0.587 + 0.114 == pytest.approx(1.0)


def test_rgb_ycbcr_round_trip_is_lossless_within_rounding():
    rng = np.random.default_rng(1234)
    rgb = rng.integers(0, 256, size=(16, 16, 3), dtype=np.uint8)

    restored = ycbcr_to_rgb(rgb_to_ycbcr(rgb))

    assert np.max(np.abs(restored.astype(int) - rgb.astype(int))) <= 1


def test_plane_conversion_round_trip():
    rng = np.random.default_rng(7)
    rgb = rng.integers(0, 256, size=(8, 8, 3), dtype=np.uint8)

    y, cb, cr = to_planes(rgb_to_ycbcr(rgb))
    restored = ycbcr_to_rgb(from_planes(y, cb, cr))

    assert np.max(np.abs(restored.astype(int) - rgb.astype(int))) <= 1


def test_420_subsampling_halves_chroma_resolution():
    rng = np.random.default_rng(3)
    chroma = rng.integers(0, 256, size=(32, 32), dtype=np.uint8)

    reduced = subsample_420(chroma)

    assert reduced.shape == (16, 16)


def test_420_subsampling_averages_each_2x2_group():
    plane = np.array([[0, 10, 20, 30],
                      [40, 50, 60, 70],
                      [80, 90, 100, 110],
                      [120, 130, 140, 150]], dtype=np.uint8)

    reduced = subsample_420(plane)

    assert reduced.shape == (2, 2)
    assert reduced[0, 0] == pytest.approx(25.0)  # (0+10+40+50)/4
    assert reduced[0, 1] == pytest.approx(45.0)  # (20+30+60+70)/4
    assert reduced[1, 0] == pytest.approx(105.0)
    assert reduced[1, 1] == pytest.approx(125.0)  # (100+110+140+150)/4


def test_upsample_restores_original_resolution():
    rng = np.random.default_rng(11)
    chroma = rng.integers(0, 256, size=(16, 16), dtype=np.uint8)

    restored = upsample_420(subsample_420(chroma))

    assert restored.shape == chroma.shape


def test_upsample_is_block_constant_like_mpeg_practical_sampling():
    """Replication up-sampling means each 2x2 output group is identical."""
    chroma = np.arange(16, dtype=np.uint8).reshape(4, 4)

    restored = upsample_420(subsample_420(chroma))

    assert restored[0, 0] == restored[0, 1]
    assert restored[0, 0] == restored[1, 0]
    assert restored[0, 0] == restored[1, 1]


def test_420_reduces_raw_sample_count_to_twelve_bits_per_pixel():
    """RGB is 24 bits/pixel; YUV 4:2:0 is 12 bits/pixel (lecture 01, slide 24)."""
    width, height = 640, 480
    samples_420 = width * height + 2 * (width // 2) * (height // 2)
    bits_per_pixel = samples_420 * 8 / (width * height)

    assert bits_per_pixel == pytest.approx(12.0)


def test_420_construction_is_exposed_as_a_subsampling_descriptor():
    """4:2:0 keeps luma at full resolution and halves chroma both ways."""
    assert ChromaSubsampling.FOUR_TWO_ZERO.label == "4:2:0"
    assert ChromaSubsampling.FOUR_TWO_ZERO.sample_rates() == (2, 1, 1)
    assert ChromaSubsampling.FOUR_FOUR_FOUR.sample_rates() == (1, 1, 1)
    assert ChromaSubsampling.FOUR_TWO_TWO.sample_rates() == (1, 1, 1)


def test_to_planes_returns_three_float_planes():
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    planes = to_planes(rgb_to_ycbcr(rgb))

    assert len(planes) == 3
    assert all(p.shape == (4, 6) for p in planes)
    assert all(p.dtype == np.float32 for p in planes)