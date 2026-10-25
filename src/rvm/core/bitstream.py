"""MSB-first bit-level reader/writer.

Every syntax element in the RVM bitstream is coded as a raw bit sequence, so
the encoder and decoder both need a cursor that does not care about byte
alignment.  Bits are emitted most-significant-first, which keeps the written
byte stream readable in the same order as the syntax diagrams.

The signed helpers use sign-magnitude rather than two's complement: residual
coefficients are small and roughly symmetric, so separating the sign from the
magnitude keeps both the zero and the small-magnitude cases short.  The sign is
placed in the most significant bit so that a decoder short of bits can still
re-read a coarse, well-formed approximation.
"""

from __future__ import annotations

__all__ = ["BitReader", "BitWriter"]


class BitWriter:
    """Accumulates bits MSB-first and packs them into bytes on demand.

    Bits are accumulated in a single integer rather than appended one at a
    time.  The bit *order* is identical either way -- most significant bit
    first -- but a whole field can be shifted in with one operation instead of
    one per bit, which matters because the entropy coder emits hundreds of
    thousands of fields per second of video.
    """

    __slots__ = ("_buffer", "_current", "_bits_in_current")

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._current = 0
        self._bits_in_current = 0

    @property
    def bit_length(self) -> int:
        """Number of bits written so far, including any partial byte."""
        return len(self._buffer) * 8 + self._bits_in_current

    def write_bits(self, value: int, width: int) -> "BitWriter":
        """Append the low ``width`` bits of ``value``, MSB first."""
        if width <= 0:
            raise ValueError(f"width must be positive, got {width}")
        if value < 0 or value >> width:
            raise ValueError(f"value {value} does not fit in {width} bits")

        self._current = (self._current << width) | value
        self._bits_in_current += width
        if self._bits_in_current >= 8:
            self._flush_bytes()
        return self

    def _flush_bytes(self) -> None:
        """Move every complete byte out of the accumulator into the buffer."""
        count = self._bits_in_current >> 3
        rest = self._bits_in_current & 7
        chunk = (self._current >> rest) & ((1 << (count * 8)) - 1)
        self._buffer += chunk.to_bytes(count, "big")
        self._bits_in_current = rest
        self._current &= (1 << rest) - 1

    def write_bit(self, bit: int) -> "BitWriter":
        """Append a single bit."""
        return self.write_bits(1 if bit else 0, 1)

    def write_signed(self, value: int, width: int) -> "BitWriter":
        """Append ``value`` as ``width`` bits of sign-magnitude coding.

        The layout is ``[sign][magnitude]``, sign first in the most significant
        bit.  Putting the sign ahead of the magnitude buys two things: zero
        degenerates to an all-zero pattern and costs a single bit, and a
        decoder that lacks the bits to reproduce a coefficient exactly can
        re-read the same bits with fewer magnitude bits to obtain a valid
        coarse value instead of noise.
        """
        if width < 2:
            raise ValueError(f"signed coding needs at least 2 bits, got {width}")

        magnitude = abs(value)
        if magnitude >> (width - 1):
            raise ValueError(
                f"signed value {value} does not fit in {width} bits of sign-magnitude"
            )

        pattern = magnitude if value >= 0 else magnitude | (1 << (width - 1))
        return self.write_bits(pattern, width)

    def byte_align(self) -> "BitWriter":
        """Pad the current partial byte with zero bits."""
        if self._bits_in_current:
            self._buffer.append((self._current << (8 - self._bits_in_current)) & 0xFF)
            self._current = 0
            self._bits_in_current = 0
        return self

    def to_bytes(self) -> bytes:
        """Flush any partial byte (zero padded) and return the payload."""
        self.byte_align()
        return bytes(self._buffer)


class BitReader:
    """Reads a byte payload back MSB-first, tracking an exact bit cursor."""

    __slots__ = ("_data", "_bit_pos")

    def __init__(self, data: bytes) -> None:
        self._data = bytes(data)
        self._bit_pos = 0

    @property
    def bit_position(self) -> int:
        return self._bit_pos

    def remaining_bits(self) -> int:
        return len(self._data) * 8 - self._bit_pos

    def read_bits(self, width: int) -> int:
        """Consume ``width`` bits and return them as an unsigned integer."""
        if width < 0:
            raise ValueError(f"width must be non-negative, got {width}")
        if width > self.remaining_bits():
            raise ValueError(
                f"cannot read {width} bits, only {self.remaining_bits()} remain"
            )

        value = 0
        for _ in range(width):
            byte = self._data[self._bit_pos >> 3]
            bit = (byte >> (7 - (self._bit_pos & 7))) & 1
            value = (value << 1) | bit
            self._bit_pos += 1
        return value

    def read_bit(self) -> int:
        return self.read_bits(1)

    def read_signed(self, width: int) -> int:
        """Consume ``width`` bits of ``[sign][magnitude]`` sign-magnitude coding.

        Reading with fewer bits than were written yields a coarser but still
        well-formed value, because the sign stays at the top and only the tail
        of the magnitude is dropped.
        """
        if width < 2:
            raise ValueError(f"signed coding needs at least 2 bits, got {width}")

        pattern = self.read_bits(width)
        magnitude = pattern & ((1 << (width - 1)) - 1)
        return -magnitude if pattern >> (width - 1) else magnitude

    def align(self) -> "BitReader":
        """Skip to the next byte boundary."""
        self._bit_pos = (self._bit_pos + 7) & ~7
        return self

    def seek_bits(self, offset: int) -> "BitReader":
        """Move the cursor to an absolute bit offset."""
        if offset < 0 or offset > self.remaining_bits() + offset:
            raise ValueError(f"cannot seek to bit offset {offset}")
        self._bit_pos = offset
        return self