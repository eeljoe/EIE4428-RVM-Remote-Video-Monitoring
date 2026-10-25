"""Tests for the MSB-first bit reader/writer used by the entropy coder."""

import pytest

from rvm.core.bitstream import BitReader, BitWriter


def test_write_zero_bits_produces_empty_payload():
    assert BitWriter().to_bytes() == b""


def test_single_bit_round_trips():
    writer = BitWriter()
    writer.write_bits(1, 1)

    assert writer.to_bytes() == b"\x80"


def test_bits_are_written_most_significant_first():
    writer = BitWriter()
    writer.write_bits(0b101, 3)

    assert writer.to_bytes() == b"\xa0"  # 101 00000


def test_sequence_of_integers_round_trips():
    writer = BitWriter()
    values = [(0b1011, 4), (0b000000, 6), (0b111111, 6)]  # exactly 16 bits

    for value, width in values:
        writer.write_bits(value, width)

    reader = BitReader(writer.to_bytes())
    for value, width in values:
        assert reader.read_bits(width) == value
    assert reader.remaining_bits() == 0


def test_unaligned_payload_is_zero_padded_to_a_byte_boundary():
    writer = BitWriter()
    writer.write_bits(0b1011, 4)  # 4 bits -> 4 padding bits

    assert writer.bit_length == 4
    assert writer.to_bytes() == b"\xb0"


def test_width_larger_than_eight_spans_byte_boundaries():
    writer = BitWriter()
    writer.write_bits(0b1_1010_0101, 9)

    assert writer.to_bytes() == b"\xd2\x80"

    reader = BitReader(writer.to_bytes())
    assert reader.read_bits(9) == 0b1_1010_0101


def test_signed_values_round_trip_through_sign_magnitude():
    writer = BitWriter()
    samples = [0, 1, -1, 127, -127, 63, -64]

    for sample in samples:
        writer.write_signed(sample, 8)

    reader = BitReader(writer.to_bytes())
    for sample in samples:
        assert reader.read_signed(8) == sample


def test_signed_zero_encodes_as_an_all_zero_field():
    """The sign-first layout makes a zero pattern, which zero-run coding exploits."""
    writer = BitWriter()
    writer.write_signed(0, 8)

    assert writer.to_bytes() == b"\x00"


def test_signed_reader_can_demote_one_bit_of_precision():
    """Sign-first layout means a narrow re-read truncates the magnitude cleanly."""
    writer = BitWriter()
    writer.write_signed(-37, 8)

    reader = BitReader(writer.to_bytes())
    assert reader.read_signed(4) == -2  # sign kept, magnitude 37 -> 0010 = 2


def test_bit_length_is_reported_before_alignment():
    writer = BitWriter()
    writer.write_bits(0b111, 3)

    assert writer.bit_length == 3


def test_bit_length_is_reported_after_alignment():
    writer = BitWriter()
    writer.write_bits(0b111, 3)
    writer.byte_align()

    assert writer.bit_length == 8


def test_alignment_pads_with_zero_bits():
    writer = BitWriter()
    writer.write_bits(0b111, 3)
    writer.byte_align()

    assert writer.to_bytes() == b"\xe0"


def test_alignment_is_idempotent_when_already_aligned():
    writer = BitWriter()
    writer.write_bits(0b1111_1111, 8)
    writer.byte_align()

    assert writer.to_bytes() == b"\xff"


def test_writing_past_a_byte_boundary_keeps_running_order():
    writer = BitWriter()
    writer.write_bits(0xFF, 8)
    writer.write_bits(0x00, 8)
    writer.write_bits(0xA5, 8)

    assert writer.to_bytes() == b"\xff\x00\xa5"


def test_reader_tracks_remaining_bits():
    reader = BitReader(b"\xff")

    reader.read_bits(3)
    assert reader.remaining_bits() == 5

    reader.read_bits(5)
    assert reader.remaining_bits() == 0


def test_reader_refuses_to_overrun():
    reader = BitReader(b"\x00")

    with pytest.raises(ValueError, match="bits"):
        reader.read_bits(9)


def test_trailing_padding_bits_are_available_to_the_reader():
    """Padding lets the decoder skip to the next byte without losing sync."""
    reader = BitReader(b"\x80")

    reader.read_bits(1)
    reader.align()

    assert reader.remaining_bits() == 0


def test_large_unsigned_values_round_trip():
    writer = BitWriter()
    writer.write_bits((1 << 31) | 12345, 32)

    reader = BitReader(writer.to_bytes())
    assert reader.read_bits(32) == (1 << 31) | 12345


def test_exp_golomb_style_variable_lengths_round_trip():
    """The rate-control log uses exponent-prefixed magnitudes."""
    writer = BitWriter()
    values = [(0, 1), (1, 3), (2, 5), (9, 7), (300, 15)]

    for value, width in values:
        writer.write_bits(value, width)

    reader = BitReader(writer.to_bytes())
    for value, width in values:
        assert reader.read_bits(width) == value


def test_writer_rejects_width_out_of_range():
    with pytest.raises(ValueError):
        BitWriter().write_bits(0, 0)


def test_writer_rejects_value_that_does_not_fit_width():
    with pytest.raises(ValueError, match="does not fit"):
        BitWriter().write_bits(4, 2)


def test_reader_start_position_can_be_seeked():
    data = b"\xde\xad\xbe\xef"
    reader = BitReader(data)

    reader.seek_bits(16)
    assert reader.read_bits(8) == 0xBE