"""Tests for the 8x8 forward/inverse DCT and the quality-scaled quantiser."""

import numpy as np
import pytest

from rvm.codec.dct import (
    BLOCK_SIZE,
    dct2d,
    dct2d_blocks,
    idct2d,
    idct2d_blocks,
)
from rvm.codec.quant import (
    LUMA_QUANT_MATRIX,
    QUANT_MIN,
    QUANT_MAX,
    QuantParams,
    build_quant_table,
    clip_quant_table,
    quality_to_qscale,
    quantize_block,
    dequantize_block,
)


def test_dct_of_a_constant_block_keeps_energy_in_dc_only():
    """A flat 8x8 block has no spatial detail, so every AC term must vanish."""
    block = np.full((8, 8), 100.0, dtype=np.float64)
    coefficients = dct2d(block)

    assert coefficients[0, 0] == pytest.approx(800.0)  # DC = 8 * 100
    assert np.max(np.abs(coefficients[1:, :])) == pytest.approx(0.0, abs=1e-9)
    assert np.max(np.abs(coefficients[:, 1:])) == pytest.approx(0.0, abs=1e-9)


def test_dct_dc_coefficient_uses_the_orthonormal_convention():
    """With the 1/4 outer factor, DC = (2/N)*mean and mean = DC/8."""
    block = np.full((8, 8), 37.0, dtype=np.float64)

    assert dct2d(block)[0, 0] == pytest.approx(8.0 * 37.0)


def test_dct_of_a_horizontal_ramp_concentrates_energy_in_one_row():
    """Energy ordering must fall with frequency for the quantiser to be useful."""
    column = np.arange(8, dtype=np.float64)
    block = np.repeat(column[None, :], 8, axis=0)
    coefficients = dct2d(block)

    dc = abs(coefficients[0, 0])
    assert dc > 0
    # No vertical variation at all: only row 0 may be non-zero.
    assert np.max(np.abs(coefficients[1:, :])) == pytest.approx(0.0, abs=1e-9)


def test_dct_is_invertible_with_high_precision():
    rng = np.random.default_rng(99)
    block = rng.uniform(-255, 255, size=(8, 8))

    restored = idct2d(dct2d(block))

    assert np.max(np.abs(restored - block)) < 1e-9


def test_dct_round_trip_on_a_natural_image_block_stays_within_rounding():
    """Floating point round error must stay far below one 8-bit level."""
    yy, xx = np.mgrid[0:64, 0:64]
    image = (127.0 + 100.0 * np.sin(xx / 6.0) * np.cos(yy / 7.0)).astype(np.float64)
    block = image[:8, :8]

    restored = idct2d(dct2d(block))

    assert np.max(np.abs(restored - block)) < 0.01


def test_dct2d_rejects_a_block_of_the_wrong_size():
    with pytest.raises(ValueError, match="8"):
        dct2d(np.zeros((4, 4)))


def test_block_size_is_eight():
    assert BLOCK_SIZE == 8


# --------------------------------------------------------------------------
# Batched transforms, used by the frame encoder
# --------------------------------------------------------------------------


def test_batched_transform_matches_the_single_block_transform():
    rng = np.random.default_rng(77)
    blocks = rng.uniform(-200, 200, size=(37, 8, 8))

    batched = dct2d_blocks(blocks)

    assert batched.shape == blocks.shape
    for index in (0, 17, 36):
        assert np.allclose(batched[index], dct2d(blocks[index]), atol=1e-9)


def test_batched_transform_round_trips():
    rng = np.random.default_rng(78)
    blocks = rng.uniform(-255, 255, size=(20, 8, 8))

    restored = idct2d_blocks(dct2d_blocks(blocks))

    assert np.max(np.abs(restored - blocks)) < 1e-9


def test_batched_transform_rejects_a_bad_stack_shape():
    with pytest.raises(ValueError, match="8, 8"):
        dct2d_blocks(np.zeros((4, 4, 4)))


# --------------------------------------------------------------------------
# Quantisation
# --------------------------------------------------------------------------


def test_luma_matrix_has_the_jpeg_shape():
    assert LUMA_QUANT_MATRIX.shape == (8, 8)
    assert LUMA_QUANT_MATRIX.dtype == np.int32


def test_luma_matrix_steps_up_with_spatial_frequency():
    """Row 0 is all low horizontal frequency and carries the smallest steps."""
    first_row = float(LUMA_QUANT_MATRIX[0].mean())
    bottom_rows = float(LUMA_QUANT_MATRIX[4:].mean())

    assert first_row < bottom_rows


def test_luma_matrix_keeps_dc_finer_than_the_high_frequency_corner():
    assert LUMA_QUANT_MATRIX[0, 0] < LUMA_QUANT_MATRIX[7, 7]


def test_luma_matrix_puts_small_steps_on_low_frequency_terms():
    """Low frequencies carry most of the energy and must survive quantisation."""
    low = LUMA_QUANT_MATRIX[:4, :4].mean()
    high = LUMA_QUANT_MATRIX[4:, 4:].mean()

    assert low < high


def test_quality_100_leaves_the_table_untouched():
    table = build_quant_table(100)

    assert np.array_equal(table, LUMA_QUANT_MATRIX)


def test_quality_1_produces_the_largest_steps():
    coarse = build_quant_table(1)

    assert coarse[0, 0] > LUMA_QUANT_MATRIX[0, 0]
    assert np.all(coarse >= LUMA_QUANT_MATRIX)


def test_bitrate_decreases_monotonically_as_quality_falls():
    qualities = [100, 80, 60, 40, 20]
    steps = [int(build_quant_table(q)[0, 0]) for q in qualities]

    # Falling quality must keep coarsening the step, i.e. steps rise.
    assert steps == sorted(steps)
    assert all(later > earlier for earlier, later in zip(steps, steps[1:]))


def test_qscale_maps_quality_onto_a_reduction_factor():
    assert quality_to_qscale(100) == pytest.approx(1.0)
    assert quality_to_qscale(50) > 1.0
    assert quality_to_qscale(1) > quality_to_qscale(50)


def test_every_table_entry_is_clamped_to_the_legal_quantiser_range():
    for quality in (1, 10, 25, 50, 75, 90, 100):
        table = build_quant_table(quality)
        assert table.min() >= QUANT_MIN
        assert table.max() <= QUANT_MAX


def test_clip_quant_table_clamps_out_of_range_entries():
    table = np.array([[0, 300], [1, 2]], dtype=np.int32)

    clipped = clip_quant_table(table)

    assert clipped.min() >= QUANT_MIN
    assert clipped.max() <= QUANT_MAX


def test_quantisation_rounds_coefficients_to_integer_levels():
    rng = np.random.default_rng(5)
    coefficients = rng.uniform(-500, 500, size=(8, 8))
    table = build_quant_table(75)

    levels = quantize_block(coefficients, table)

    assert levels.dtype == np.int32
    assert np.allclose(levels, np.round(coefficients / table))


def test_quantise_dequantise_reconstructs_when_the_step_is_one():
    coefficients = np.arange(64, dtype=np.float64).reshape(8, 8)
    table = np.ones((8, 8), dtype=np.int32)

    restored = dequantize_block(quantize_block(coefficients, table), table)

    assert np.allclose(restored, coefficients)


def test_higher_quality_reconstructs_more_closely():
    """Lower QP means finer steps, so the quantiser error must shrink."""
    rng = np.random.default_rng(21)
    coefficients = rng.normal(0, 40, size=(8, 8))

    errors = []
    for quality in (25, 50, 75, 100):
        table = build_quant_table(quality)
        restored = dequantize_block(quantize_block(coefficients, table), table)
        errors.append(float(np.mean((restored - coefficients) ** 2)))

    assert errors == sorted(errors, reverse=True)


def test_quant_params_expose_the_twelve_bit_qp_style_level():
    params = QuantParams(quality=60)

    assert 1 <= params.qp <= 51
    assert params.quality == 60


def test_quant_params_qp_moves_opposite_to_quality():
    low_quality = QuantParams(quality=10).qp
    high_quality = QuantParams(quality=90).qp

    assert low_quality > high_quality


def test_quant_params_can_be_clamped_to_a_qp_window():
    """Rate control needs to hold QP inside a band around the previous frame."""
    too_fine = QuantParams(quality=90, min_qp=30, max_qp=40)
    too_coarse = QuantParams(quality=10, min_qp=30, max_qp=40)

    assert too_fine.qp == 30  # derived QP 6 is too fine, lifted to the floor
    assert too_coarse.qp == 40  # derived QP 46 is too coarse, pulled to the ceiling


def test_quant_params_accept_an_explicit_qp_override():
    params = QuantParams(quality=90, qp=12)

    assert params.qp == 12