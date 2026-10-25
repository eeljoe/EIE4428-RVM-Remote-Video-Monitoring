"""Tests for objective quality metrics: PSNR and SSIM."""

import numpy as np
import pytest
from scenegen import structured_shift_scene

from rvm.analysis.quality import mse, psnr, ssim


def test_identical_images_have_infinite_psnr():
    frame = np.random.default_rng(1).integers(0, 256, size=(64, 64)).astype(np.uint8)

    assert psnr(frame, frame) == pytest.approx(float("inf"))


def test_psnr_of_a_known_constant_error():
    """A flat error of amplitude e over a 255-peak image gives a closed form."""
    original = np.full((32, 32), 100, dtype=np.uint8)
    corrupted = np.full((32, 32), 104, dtype=np.uint8)  # error = 4

    expected = 10.0 * np.log10(255.0**2 / 16.0)

    assert psnr(original, corrupted) == pytest.approx(expected, rel=1e-6)


def test_psnr_falls_as_the_error_grows():
    original = np.full((32, 32), 100, dtype=np.uint8)
    small = np.full((32, 32), 101, dtype=np.uint8)
    large = np.full((32, 32), 120, dtype=np.uint8)

    assert psnr(original, small) > psnr(original, large)


def test_psnr_is_symmetric_in_its_arguments():
    a = np.random.default_rng(2).integers(0, 256, size=(16, 16)).astype(np.uint8)
    b = np.random.default_rng(3).integers(0, 256, size=(16, 16)).astype(np.uint8)

    assert psnr(a, b) == pytest.approx(psnr(b, a))


def test_mse_of_identical_images_is_zero():
    frame = np.arange(256, dtype=np.uint8).reshape(16, 16)

    assert mse(frame, frame) == pytest.approx(0.0)


def test_metrics_reject_mismatched_shapes():
    a = np.zeros((16, 16), dtype=np.uint8)
    b = np.zeros((16, 8), dtype=np.uint8)

    with pytest.raises(ValueError, match="shape"):
        psnr(a, b)


def test_metrics_accept_colour_and_measure_on_luma():
    rng = np.random.default_rng(9)
    original = rng.integers(0, 256, size=(16, 16, 3)).astype(np.uint8)
    noisy = np.clip(
        original.astype(int) + rng.integers(-4, 5, size=(16, 16, 3)), 0, 255
    ).astype(np.uint8)

    colour_score = psnr(original, noisy)
    luma_score = psnr(
        0.299 * original[..., 0] + 0.587 * original[..., 1] + 0.114 * original[..., 2],
        0.299 * noisy[..., 0] + 0.587 * noisy[..., 1] + 0.114 * noisy[..., 2],
    )

    assert colour_score == pytest.approx(luma_score, rel=1e-9)


def test_metrics_reject_an_image_with_an_unexpected_channel_count():
    a = np.zeros((16, 16, 4), dtype=np.uint8)

    with pytest.raises(ValueError, match="H, W, 3"):
        psnr(a, a)


def test_a_good_codec_round_trip_scores_well_above_thirty_db():
    rng = np.random.default_rng(4)
    original = rng.integers(0, 256, size=(32, 32)).astype(np.uint8)
    corrupted = np.clip(original.astype(int) + rng.integers(-3, 4, size=(32, 32)), 0, 255)
    corrupted = corrupted.astype(np.uint8)

    assert psnr(original, corrupted) > 35.0


def test_ssim_of_identical_images_is_one():
    frame = np.random.default_rng(5).integers(0, 256, size=(64, 64)).astype(np.uint8)

    assert ssim(frame, frame) == pytest.approx(1.0, abs=1e-9)


def test_ssim_degrades_under_noise():
    """SSIM needs structure to discriminate: on white noise it saturates."""
    rng = np.random.default_rng(6)
    _, luma = structured_shift_scene(64, 64, seed=0)
    original = np.clip(luma, 0, 255).astype(np.uint8)
    noisy = np.clip(
        original.astype(int) + rng.integers(-20, 21, size=(64, 64)), 0, 255
    ).astype(np.uint8)

    assert ssim(original, original) == pytest.approx(1.0, abs=1e-9)
    assert ssim(original, noisy) < 0.9


def test_ssim_penalises_blur_more_than_mild_noise():
    """SSIM is sensitive to structural loss, which is what a codec degrades."""
    rows, columns = np.mgrid[0:64, 0:64]
    sharp = (127.0 + 100.0 * np.sin(columns / 3.0)).astype(np.uint8)
    blurred = sharp.copy()
    blurred[:, 1:-1] = ((sharp[:, :-2].astype(int) + sharp[:, 2:].astype(int)) // 2).astype(np.uint8)
    mild = np.clip(sharp.astype(int) + 3, 0, 255).astype(np.uint8)

    assert ssim(sharp, blurred) < ssim(sharp, mild)


def test_ssim_stays_within_the_negative_one_to_one_range():
    rng = np.random.default_rng(7)
    a = rng.integers(0, 256, size=(32, 32)).astype(np.uint8)
    b = np.zeros((32, 32), dtype=np.uint8)

    assert -1.0 <= ssim(a, b) <= 1.0


def test_ssim_matches_psnr_on_a_uniform_offset():
    """A flat DC shift changes brightness but not local structure."""
    original = np.full((32, 32), 100, dtype=np.uint8)
    shifted = np.full((32, 32), 104, dtype=np.uint8)

    # Luminance/contrast terms are unchanged, so SSIM stays very high even
    # though PSNR reports a finite error.
    assert ssim(original, shifted) > 0.99