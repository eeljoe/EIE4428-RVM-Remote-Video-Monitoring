"""Entropy coding of quantised transform coefficients.

Quantisation alone does not save bits.  What makes a transform codec compact is
that after zig-zag scanning the 64 coefficients of a block are mostly zero and
the few surviving values are small.  The entropy coder exploits exactly that:
it walks the coefficients in zig-zag order, codes the *gap* between successive
non-zero values, and then codes the magnitude with an Exp-Golomb code whose
length grows only with the logarithm of the value.

The zig-zag order matters because it is monotone in spatial frequency, so the
long gaps it produces land at the high-frequency end where the coefficients are
usually zero.  Coding in raster order would interleave those zeros with the
large low-frequency values and destroy the run structure.

Every coefficient value here is losslessly recoverable.  Truncation is handled
one layer up, by not sending the whole block.
"""

from __future__ import annotations

import numpy as np

from ..core.bitstream import BitReader, BitWriter
from .dct import BLOCK_SIZE

__all__ = [
    "EOB_TOKEN",
    "ZIGZAG_INDEX",
    "decode_block_coefficients",
    "deinterleave",
    "encode_block_coefficients",
    "encode_plane_coefficients",
    "interleave",
    "read_se",
    "read_ue",
    "rle_decode",
    "rle_encode",
    "write_se",
    "write_ue",
    "zigzag_scan",
]

# Raster indices of the 64 coefficients in zig-zag (diagonal) scan order.
ZIGZAG_INDEX = np.array(
    [
        [0, 1, 8, 16, 9, 2, 3, 10],
        [17, 24, 32, 25, 18, 11, 4, 5],
        [12, 19, 26, 33, 40, 48, 41, 34],
        [27, 20, 13, 6, 7, 14, 21, 28],
        [35, 42, 49, 56, 57, 50, 43, 36],
        [29, 22, 15, 23, 30, 37, 44, 51],
        [58, 59, 52, 45, 38, 31, 39, 46],
        [53, 60, 61, 54, 47, 55, 62, 63],
    ],
    dtype=np.int32,
)

# Sentinel written in place of "index of the last non-zero coefficient".
EOB_TOKEN = 0


# --------------------------------------------------------------------------
# Exp-Golomb codes
# --------------------------------------------------------------------------


def write_ue(writer: BitWriter, value: int) -> BitWriter:
    """Write an unsigned Exp-Golomb code ``ue(v)``."""
    if value < 0:
        raise ValueError(f"ue(v) is defined for non-negative values, got {value}")

    encoded = value + 1
    length = int(encoded).bit_length()

    # The code is (length - 1) leading zeros followed by ``encoded`` in exactly
    # ``length`` bits, so the whole thing is ``encoded`` sitting in the low
    # ``length`` bits of a field that is ``2 * length - 1`` bits wide.  Writing
    # it as one field instead of two is worth it: the entropy coder emits
    # hundreds of thousands of these per second of video.
    #
    # ue(0) is the single bit '1', so the zero prefix is skipped entirely.
    writer.write_bits(encoded, 2 * length - 1)
    return writer


def read_ue(reader: BitReader) -> int:
    """Read an unsigned Exp-Golomb code ``ue(v)``."""
    leading_zeros = 0
    while reader.read_bit() == 0:
        leading_zeros += 1
        if leading_zeros > 32:
            raise ValueError("corrupt Exp-Golomb code: too many leading zeros")

    if leading_zeros == 0:
        return 0

    suffix = reader.read_bits(leading_zeros)
    return (1 << leading_zeros) - 1 + suffix


def write_se(writer: BitWriter, value: int) -> BitWriter:
    """Write a signed Exp-Golomb code ``se(v)``, zig-zag mapped onto ``ue``."""
    return write_ue(writer, 2 * abs(value) - (1 if value > 0 else 0))


def read_se(reader: BitReader) -> int:
    """Read a signed Exp-Golomb code ``se(v)``."""
    mapped = read_ue(reader)
    return (mapped + 1) // 2 if mapped & 1 else -(mapped // 2)


# --------------------------------------------------------------------------
# Explicit run-length coding
# --------------------------------------------------------------------------


def rle_encode(sequence: list[int]) -> list[tuple[int, int]]:
    """Encode a sequence as ``(zero_run, value)`` pairs.

    Trailing zeros are represented by a final pair carrying a zero value, which
    is what lets the decoder recover the original length.
    """
    pairs: list[tuple[int, int]] = []
    run = 0

    for value in sequence:
        if value == 0:
            run += 1
            continue
        pairs.append((run, value))
        run = 0

    if run or not pairs:
        pairs.append((run, 0))
    return pairs


def rle_decode(pairs: list[tuple[int, int]]) -> list[int]:
    """Inverse of :func:`rle_encode`.

    A pair whose value is zero is the terminating pair: it contributes its run
    of zeros and nothing more, which is what keeps the round trip exact.
    """
    sequence: list[int] = []
    for run, value in pairs:
        sequence.extend([0] * run)
        if value == 0:
            break
        sequence.append(value)
    return sequence


# --------------------------------------------------------------------------
# Zig-zag helpers
# --------------------------------------------------------------------------


def zigzag_scan(block: np.ndarray) -> np.ndarray:
    """Reorder an 8x8 coefficient block into zig-zag scan order."""
    if block.shape != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(f"expected an 8x8 block, got shape {block.shape}")
    return block.reshape(-1)[ZIGZAG_INDEX.reshape(-1)]


def interleave(blocks: np.ndarray) -> np.ndarray:
    """Flatten ``(N, 8, 8)`` blocks into ``(N, 64)`` zig-zag scan order."""
    if blocks.ndim != 3 or blocks.shape[1:] != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(f"expected (N, 8, 8) blocks, got shape {blocks.shape}")
    return blocks.reshape(blocks.shape[0], -1)[:, ZIGZAG_INDEX.reshape(-1)]


def deinterleave(sequence: np.ndarray) -> np.ndarray:
    """Inverse of :func:`interleave`.

    Accepts a single ``(64,)`` scan sequence or a batch ``(N, 64)``.
    """
    if sequence.ndim == 1:
        if sequence.shape != (64,):
            raise ValueError(
                f"expected a 64-value scan sequence, got shape {sequence.shape}"
            )
        block = np.empty(64, dtype=sequence.dtype)
        block[ZIGZAG_INDEX.reshape(-1)] = sequence
        return block.reshape(BLOCK_SIZE, BLOCK_SIZE)

    if sequence.ndim == 2 and sequence.shape[1] == 64:
        batches = np.empty((sequence.shape[0], 64), dtype=sequence.dtype)
        batches[:, ZIGZAG_INDEX.reshape(-1)] = sequence
        return batches.reshape(-1, BLOCK_SIZE, BLOCK_SIZE)

    raise ValueError(
        f"expected a (64,) or (N, 64) scan sequence, got shape {sequence.shape}"
    )


# --------------------------------------------------------------------------
# Block coefficient coder
# --------------------------------------------------------------------------


def encode_block_coefficients(writer: BitWriter, levels: np.ndarray) -> BitWriter:
    """Write one quantised 8x8 block into the bitstream.

    Layout: ``ue(last_scan_position + 1)`` followed, for each non-zero
    coefficient up to that position, by ``ue(zero_run)`` and ``se(level)``.
    A block with nothing above zero costs the single ``EOB_TOKEN`` code.
    """
    if levels.shape != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(f"expected an 8x8 block, got shape {levels.shape}")

    scan = zigzag_scan(levels.astype(np.int64))
    non_zero = np.nonzero(scan)[0]
    if non_zero.size == 0:
        return write_ue(writer, EOB_TOKEN)

    last = int(non_zero[-1])
    write_ue(writer, last + 1)

    # The scan is read element by element below, so it is converted to Python
    # integers once: indexing a NumPy array returns a NumPy scalar, and the
    # per-element overhead of that dominates the loop.
    values = scan.tolist()
    run = 0
    for position in range(last + 1):
        value = values[position]
        if value == 0:
            run += 1
            continue
        write_ue(writer, run)
        write_se(writer, value)
        run = 0

    return writer


def decode_block_coefficients(reader: BitReader) -> np.ndarray:
    """Read one quantised 8x8 block written by :func:`encode_block_coefficients`."""
    last_plus_one = read_ue(reader)

    if last_plus_one == EOB_TOKEN:
        return np.zeros((BLOCK_SIZE, BLOCK_SIZE), dtype=np.int32)

    last = last_plus_one - 1
    if last < 0 or last >= 64:
        raise ValueError(f"invalid last coefficient position {last}")

    scan = np.zeros(64, dtype=np.int64)
    position = 0
    while position <= last:
        run = read_ue(reader)
        position += run
        if position > last:
            raise ValueError("zero run overruns the coded coefficient range")
        scan[position] = read_se(reader)
        position += 1

    return deinterleave(scan).astype(np.int32)


def encode_plane_coefficients(writer: BitWriter, levels: np.ndarray) -> BitWriter:
    """Write every block of a plane into the bitstream.

    This is the batch form of :func:`encode_block_coefficients` and produces
    exactly the same bits.  It exists because the per-block form spent most of
    its time in NumPy call overhead: a 320x240 picture is 1800 blocks, and
    each one paid for a scan, a non-zero search and a loop over 64 positions
    whether or not anything was there to code.

    Here the scan and the non-zero search are done once for the whole plane,
    and the loop visits only the coefficients that actually carry a value.
    """
    if levels.ndim != 3 or levels.shape[1:] != (BLOCK_SIZE, BLOCK_SIZE):
        raise ValueError(f"expected (N, 8, 8) blocks, got shape {levels.shape}")

    scan = interleave(levels.astype(np.int32))
    mask = scan != 0

    # The coefficients that survive, listed block by block and, inside a
    # block, in scan order.
    blocks, positions = np.nonzero(mask)
    values = scan[blocks, positions]

    # The position of the last non-zero coefficient of each block, or -1 for a
    # block with nothing above zero.
    last = np.where(
        mask.any(axis=1), 63 - np.argmax(mask[:, ::-1], axis=1), -1
    )

    blocks_list = blocks.tolist()
    positions_list = positions.tolist()
    values_list = values.tolist()
    last_list = last.tolist()

    count = len(blocks_list)
    cursor = 0
    for block in range(len(last_list)):
        end = last_list[block]
        if end < 0:
            write_ue(writer, EOB_TOKEN)
            continue

        write_ue(writer, end + 1)

        previous = -1
        while cursor < count and blocks_list[cursor] == block:
            position = positions_list[cursor]
            write_ue(writer, position - previous - 1)
            write_se(writer, values_list[cursor])
            previous = position
            cursor += 1

    return writer