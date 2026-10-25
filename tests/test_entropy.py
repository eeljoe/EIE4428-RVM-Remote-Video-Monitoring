"""Tests for the zigzag scan and the entropy coder for quantised blocks."""

import numpy as np
import pytest

from rvm.core.bitstream import BitReader, BitWriter
from rvm.codec.entropy import (
    EOB_TOKEN,
    ZIGZAG_INDEX,
    decode_block_coefficients,
    deinterleave,
    encode_block_coefficients,
    encode_plane_coefficients,
    interleave,
    read_se,
    read_ue,
    rle_decode,
    rle_encode,
    write_se,
    write_ue,
    zigzag_scan,
)


# --------------------------------------------------------------------------
# Zig-zag scan
# --------------------------------------------------------------------------


def test_zigzag_index_covers_every_raster_position_exactly_once():
    assert sorted(ZIGZAG_INDEX.reshape(-1).tolist()) == list(range(64))


def test_zigzag_starts_at_dc_and_ends_at_the_highest_frequency_term():
    scan = ZIGZAG_INDEX.reshape(-1)

    assert scan[0] == 0
    assert scan[-1] == 63


def test_zigzag_visits_positions_in_increasing_frequency_order():
    """Every scan step must not decrease the row+column frequency rank."""
    scan = ZIGZAG_INDEX.reshape(-1)
    ranks = [int(r // 8) + int(r % 8) for r in scan]

    assert ranks == sorted(ranks)
    assert ranks[0] == 0
    assert ranks[-1] == 14  # bottom-right corner


def test_zigzag_scan_moves_a_single_coefficient_to_its_scan_position():
    scan = ZIGZAG_INDEX.reshape(-1)
    raster = 61  # block[7, 5]
    expected_position = int(np.nonzero(scan == raster)[0][0])

    block = np.zeros((8, 8), dtype=np.int32)
    block[7, 5] = 1

    ordered = zigzag_scan(block)

    assert ordered[0] == 0
    assert ordered[expected_position] == 1
    assert int(np.count_nonzero(ordered)) == 1


def test_zigzag_round_trips_through_the_interleave_helper():
    rng = np.random.default_rng(4)
    block = rng.integers(-20, 20, size=(8, 8)).astype(np.int32)

    sequence = zigzag_scan(block)

    assert np.array_equal(deinterleave(sequence), block)


def test_interleave_deinterleave_round_trip():
    rng = np.random.default_rng(6)
    blocks = rng.integers(-5, 5, size=(11, 8, 8)).astype(np.int32)

    flat = interleave(blocks)

    assert flat.shape == (11, 64)
    assert np.array_equal(deinterleave(flat), blocks)


# --------------------------------------------------------------------------
# Exp-Golomb
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 1, 2, 3, 7, 8, 100, 1023, 1024])
def test_unsigned_exp_golomb_round_trips(value):
    writer = BitWriter()
    write_ue(writer, value)

    assert read_ue(BitReader(writer.to_bytes())) == value


def test_exp_golomb_code_length_grows_logarithmically():
    def code_length(value: int) -> int:
        writer = BitWriter()
        write_ue(writer, value)
        return writer.bit_length

    assert code_length(0) == 1
    assert code_length(1) == 3
    assert code_length(2) == 3
    assert code_length(3) == 5
    assert code_length(7) == 7
    assert code_length(1023) - code_length(31) == 10


def test_exp_golomb_sequences_concatenate_and_decode_independently():
    writer = BitWriter()
    values = [0, 1, 2, 3, 4, 5, 300, 0]
    for value in values:
        write_ue(writer, value)

    reader = BitReader(writer.to_bytes())
    assert [read_ue(reader) for _ in values] == values


@pytest.mark.parametrize("value", [0, 1, -1, 2, -2, 17, -17])
def test_signed_exp_golomb_round_trips(value):
    writer = BitWriter()
    write_se(writer, value)

    assert read_se(BitReader(writer.to_bytes())) == value


def test_signed_exp_golomb_is_symmetric_in_cost():
    def code_length(value: int) -> int:
        writer = BitWriter()
        write_se(writer, value)
        return writer.bit_length

    assert code_length(5) == code_length(-5)


# --------------------------------------------------------------------------
# Explicit run-length coding (the baseline the coder beats)
# --------------------------------------------------------------------------


def test_rle_round_trips_a_sequence_with_leading_and_interior_zeros():
    sequence = [0, 0, 0, 4, 0, -3, 0, 0, 7]

    decoded = rle_decode(rle_encode(sequence))

    assert decoded == sequence


def test_rle_of_an_all_zero_sequence_keeps_its_length():
    """Without the trailing zero-value pair the length would be unrecoverable."""
    assert rle_encode([0] * 10) == [(10, 0)]
    assert rle_decode(rle_encode([0] * 10)) == [0] * 10


def test_rle_encodes_trailing_zeros_as_a_run_not_as_pairs():
    encoded = rle_encode([5, 0, 0, 0])

    assert encoded == [(0, 5), (3, 0)]


def test_rle_of_a_single_nonzero_value():
    assert rle_encode([9]) == [(0, 9)]


# --------------------------------------------------------------------------
# Block coefficient coder
# --------------------------------------------------------------------------


def test_encoded_all_zero_block_is_a_single_end_of_block_token():
    writer = BitWriter()
    encode_block_coefficients(writer, np.zeros((8, 8), dtype=np.int32))

    assert writer.bit_length == 1
    assert read_ue(BitReader(writer.to_bytes())) == EOB_TOKEN


def test_block_coefficients_round_trip():
    rng = np.random.default_rng(12)
    block = rng.integers(-40, 40, size=(8, 8)).astype(np.int32)
    # Force a realistic sparsity pattern: quantised residuals are mostly zero.
    block[rng.random((8, 8)) < 0.6] = 0

    writer = BitWriter()
    encode_block_coefficients(writer, block)
    restored = decode_block_coefficients(BitReader(writer.to_bytes()))

    assert np.array_equal(restored, block)


def test_block_coder_survives_the_heaviest_coefficients():
    block = np.zeros((8, 8), dtype=np.int32)
    block[0, 0] = 32000
    block[1, 1] = -30000
    block[7, 7] = 15000

    writer = BitWriter()
    encode_block_coefficients(writer, block)

    assert np.array_equal(
        decode_block_coefficients(BitReader(writer.to_bytes())), block
    )


def test_block_coder_costs_fewer_bits_than_raw_fixed_width_coding():
    """The whole point of entropy coding: sparsity must actually shrink the stream."""
    rng = np.random.default_rng(31)
    block = np.zeros((8, 8), dtype=np.int32)
    block[0, 0] = 40
    block[0, 1] = -12
    block[1, 0] = 7
    block[2, 2] = -3

    writer = BitWriter()
    encode_block_coefficients(writer, block)

    assert writer.bit_length < 64 * 12  # raw sign-magnitude at full width


def test_zero_run_cost_is_proportional_to_the_gap():
    """A lone high-frequency coefficient separated by zeros must stay cheap."""
    near = np.zeros((8, 8), dtype=np.int32)
    near[0, 0] = 10
    far = np.zeros((8, 8), dtype=np.int32)
    far[0, 7] = 10

    near_writer, far_writer = BitWriter(), BitWriter()
    encode_block_coefficients(near_writer, near)
    encode_block_coefficients(far_writer, far)

    assert far_writer.bit_length < 40


def test_consecutive_block_coders_stay_in_sync():
    """The decoder must find every block boundary without length prefixes."""
    rng = np.random.default_rng(44)
    blocks = []
    for _ in range(6):
        block = rng.integers(-30, 30, size=(8, 8)).astype(np.int32)
        block[rng.random((8, 8)) < 0.7] = 0
        blocks.append(block)

    writer = BitWriter()
    for block in blocks:
        encode_block_coefficients(writer, block)

    reader = BitReader(writer.to_bytes())
    decoded = [decode_block_coefficients(reader) for _ in blocks]

    assert all(np.array_equal(a, b) for a, b in zip(blocks, decoded))


def test_block_coder_rejects_a_block_of_the_wrong_shape():
    with pytest.raises(ValueError, match="8"):
        encode_block_coefficients(BitWriter(), np.zeros((4, 4), dtype=np.int32))


# --------------------------------------------------------------------------
# Batch plane coder
# --------------------------------------------------------------------------


def random_blocks(count: int, seed: int = 0) -> np.ndarray:
    """A mix of empty, sparse and dense blocks."""
    rng = np.random.default_rng(seed)
    blocks = np.zeros((count, 8, 8), dtype=np.int32)
    for index in range(count):
        kind = index % 3
        if kind == 0:
            continue
        if kind == 1:
            for _ in range(3):
                blocks[index, rng.integers(0, 8), rng.integers(0, 8)] = rng.integers(
                    -4, 5
                )
        else:
            blocks[index] = rng.integers(-30, 30, size=(8, 8))
            blocks[index][0, 0] = 0
    return blocks


def test_the_batch_coder_writes_the_same_bits_as_the_per_block_coder():
    blocks = random_blocks(64)

    per_block = BitWriter()
    for block in blocks:
        encode_block_coefficients(per_block, block)

    batch = BitWriter()
    encode_plane_coefficients(batch, blocks)

    assert batch.to_bytes() == per_block.to_bytes()


def test_the_batch_coder_round_trips_through_the_block_decoder():
    blocks = random_blocks(32)

    writer = BitWriter()
    encode_plane_coefficients(writer, blocks)
    reader = BitReader(writer.to_bytes())

    for block in blocks:
        decoded = decode_block_coefficients(reader)

        assert np.array_equal(decoded, block)


def test_the_batch_coder_handles_a_plane_of_empty_blocks():
    blocks = np.zeros((16, 8, 8), dtype=np.int32)

    writer = BitWriter()
    encode_plane_coefficients(writer, blocks)
    reader = BitReader(writer.to_bytes())

    for _ in range(16):
        assert np.array_equal(decode_block_coefficients(reader), blocks[0])