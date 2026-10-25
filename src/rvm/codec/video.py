"""The hybrid video encoder and its matching decoder.

This is the assembled codec: a block-based hybrid transform coder, the same
architecture as MPEG and H.26x.  Per picture the pipeline is

    source -> (subtract prediction) -> DCT -> quantise -> entropy code -> bits

with a reconstruction branch running the inverse operations back into a
reference memory, so encoder and decoder stay bit-exactly in step.  That
reconstruction branch is not optional bookkeeping: if the encoder's reference
ever drifts from the decoder's, every subsequent predicted frame inherits the
error and never recovers.

Picture types follow the course's classification:

* **I frame** -- coded without prediction.  Expensive, but self-contained, so
  it is what a new receiver needs and what the server sends after a join or a
  packet loss.
* **P frame** -- motion-compensated prediction from the previous reconstructed
  frame, with only the residual transformed.  Cheap, and the reason a monitoring
  stream is affordable at all: the scene rarely changes completely between
  frames.

Chroma is carried at half resolution in both directions (4:2:0), which is what
turns 24 bits per pixel of RGB into 12 before any compression happens.

Rate control runs between the two: the encoder reports the real size of each
picture to the virtual buffer, and the buffer returns the QP for the next one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..core.bitstream import BitReader, BitWriter
from ..core.colorspace import (
    from_planes,
    rgb_to_ycbcr,
    subsample_420,
    to_planes,
    upsample_420,
    ycbcr_to_rgb,
)
from .dct import BLOCK_SIZE, dct2d_blocks, idct2d_blocks
from .entropy import decode_block_coefficients, encode_plane_coefficients, write_se
from .motion import MotionField, compensate, estimate_motion
from .quant import QuantParams
from .ratecontrol import FrameType, RateController

__all__ = ["EncodedFrame", "VideoDecoder", "VideoEncoder", "MAGIC", "VERSION"]

MAGIC = b"RV"
VERSION = 1

_IS_INTRA = 1
_IS_INTER = 0
_QP_BITS = 6  # QP 1..51 fits in six bits once the one is subtracted


@dataclass(frozen=True)
class EncodedFrame:
    """One coded picture plus the metadata the receiver needs to present it."""

    data: bytes
    frame_type: FrameType
    is_keyframe: bool
    qp: int
    frame_index: int
    timestamp: float
    encode_time_ms: float
    width: int
    height: int
    chroma_width: int
    chroma_height: int
    motion_magnitude: float = 0.0

    @property
    def size(self) -> int:
        """Payload size in bytes."""
        return len(self.data)


def _grid(width: int, height: int) -> tuple[int, int]:
    """Return ``(block_rows, block_cols)`` for a plane of the given size."""
    return height // BLOCK_SIZE, width // BLOCK_SIZE


def _plane_blocks(plane: np.ndarray) -> np.ndarray:
    """Split a plane into ``(rows * cols, 8, 8)`` blocks in raster order."""
    rows, columns = _grid(plane.shape[1], plane.shape[0])
    aligned = plane[: rows * BLOCK_SIZE, : columns * BLOCK_SIZE]
    return aligned.reshape(
        rows, BLOCK_SIZE, columns, BLOCK_SIZE
    ).transpose(0, 2, 1, 3).reshape(-1, BLOCK_SIZE, BLOCK_SIZE)


def _blocks_to_plane(blocks: np.ndarray, width: int, height: int) -> np.ndarray:
    """Inverse of :func:`_plane_blocks`."""
    rows, columns = _grid(width, height)
    arranged = blocks.reshape(rows, columns, BLOCK_SIZE, BLOCK_SIZE)
    return arranged.transpose(0, 2, 1, 3).reshape(rows * BLOCK_SIZE, columns * BLOCK_SIZE)


def _write_motion_field(writer: BitWriter, field: MotionField) -> None:
    """Write a per-block motion field, scan order."""
    dx = field.dx.reshape(-1).tolist()
    dy = field.dy.reshape(-1).tolist()
    for x, y in zip(dx, dy):
        write_se(writer, x)
        write_se(writer, y)


def _read_motion_field(reader: BitReader, rows: int, columns: int) -> MotionField:
    from .entropy import read_se

    dx = np.empty(rows * columns, dtype=np.int32)
    dy = np.empty(rows * columns, dtype=np.int32)
    for index in range(rows * columns):
        dx[index] = read_se(reader)
        dy[index] = read_se(reader)

    return MotionField(
        dx=dx.reshape(rows, columns),
        dy=dy.reshape(rows, columns),
        cost=np.zeros((rows, columns), dtype=np.float64),
    )


def _mean_magnitude(field: MotionField) -> float:
    return float(np.mean(np.hypot(field.dx, field.dy)))


class VideoEncoder:
    """Block-based hybrid encoder with virtual-buffer rate control."""

    def __init__(
        self,
        width: int,
        height: int,
        target_bitrate: int = 1_000_000,
        frame_rate: float = 25.0,
        gop_size: int = 30,
        search_range: int = 8,
        refine_window: int = 2,
    ) -> None:
        if width % 16 or height % 16:
            raise ValueError(
                f"frame {width}x{height} must be a multiple of 16 so that both "
                "the luma plane and the half-resolution chroma planes stay block aligned"
            )
        if target_bitrate <= 0:
            raise ValueError(f"target_bitrate must be positive, got {target_bitrate}")
        if frame_rate <= 0:
            raise ValueError(f"frame_rate must be positive, got {frame_rate}")

        self.width = int(width)
        self.height = int(height)
        self.frame_rate = float(frame_rate)
        self.gop_size = max(1, int(gop_size))
        self.search_range = int(search_range)
        self.refine_window = int(refine_window)

        self.rate_controller = RateController(
            target_bitrate=target_bitrate,
            frame_rate=frame_rate,
            width=width,
            height=height,
        )

        self._frame_index = 0
        self._reference: list[np.ndarray] | None = None
        self._last_keyframe_index = -self.gop_size

    # -- public API ----------------------------------------------------------

    @property
    def chroma_width(self) -> int:
        return self.width // 2

    @property
    def chroma_height(self) -> int:
        return self.height // 2

    @property
    def frame_index(self) -> int:
        return self._frame_index

    @property
    def reconstruction_luma(self) -> np.ndarray | None:
        """The reconstructed luma plane of the last picture.

        This is the picture the receiver will actually display once the bit
        stream has been decoded, so comparing the source against it measures
        the distortion the codec really introduced rather than comparing the
        source with itself.
        """
        if self._reference is None:
            return None
        return self._reference[0]

    @property
    def reconstruction_rgb(self) -> np.ndarray | None:
        """The reconstructed picture of the last frame, as an RGB image.

        This is what a receiver displays after decoding the bitstream.  The
        encoder's reconstruction branch and the decoder run the same inverse
        operations on the same quantised levels, so the two agree -- the test
        suite asserts that a coded and decoded sequence stays synchronised.

        Serving *this* to the browser rather than the raw camera frame is what
        makes the demonstration honest: the operator sees the compressed
        video, and the difference between the two views is the codec's own
        distortion, visible rather than claimed.
        """
        if self._reference is None:
            return None
        luma, cb, cr = self._reference
        return ycbcr_to_rgb(from_planes(luma, upsample_420(cb), upsample_420(cr)))

    def encode(self, frame: np.ndarray, force_keyframe: bool = False) -> EncodedFrame:
        """Encode one RGB frame into a coded picture."""
        frame = np.asarray(frame)
        if frame.shape != (self.height, self.width, 3):
            raise ValueError(
                f"expected an RGB frame of shape {(self.height, self.width, 3)}, "
                f"got {frame.shape}"
            )

        started = time.perf_counter()

        luma, cb, cr = to_planes(rgb_to_ycbcr(frame))
        planes = [luma, subsample_420(cb), subsample_420(cr)]

        is_intra = (
            force_keyframe
            or self._reference is None
            or (self._frame_index - self._last_keyframe_index) >= self.gop_size
        )

        # Rate control governs every picture, keyframes included. Pinning an
        # intra picture to the start-of-sequence QP would let it burst straight
        # through the buffer, which is exactly the picture a receiver is least
        # able to absorb.
        qp = self.rate_controller.current_qp
        params = QuantParams(quality=100.0, qp=qp)
        luma_table = params.luma_table()
        chroma_table = params.chroma_table()

        writer = BitWriter()
        if is_intra:
            _write_sequence_header(writer, self.width, self.height, luma_table, chroma_table)

        _write_picture_header(writer, is_intra, params.qp)

        reconstructed: list[np.ndarray] = []
        motion_magnitude = 0.0

        for index, plane in enumerate(planes):
            table = luma_table if index == 0 else chroma_table

            if is_intra:
                residual = plane
                prediction = np.zeros_like(plane)
            else:
                assert self._reference is not None
                reference = self._reference[index]
                field = estimate_motion(
                    reference,
                    plane,
                    search_range=self.search_range,
                    refine_window=self.refine_window,
                )
                motion_magnitude += _mean_magnitude(field)
                prediction = compensate(reference, field)
                residual = plane - prediction
                _write_motion_field(writer, field)

            levels = quantize_residual(residual, table)
            encode_plane_coefficients(writer, levels)

            reconstructed.append(
                np.clip(
                    prediction
                    + _residual_from_levels(levels, table, plane.shape[1], plane.shape[0]),
                    0.0,
                    255.0,
                )
            )

        payload = writer.to_bytes()

        self._reference = reconstructed
        if is_intra:
            self._last_keyframe_index = self._frame_index

        self.rate_controller.update(len(payload) * 8, FrameType.I if is_intra else FrameType.P)

        encoded = EncodedFrame(
            data=payload,
            frame_type=FrameType.I if is_intra else FrameType.P,
            is_keyframe=is_intra,
            qp=params.qp,
            frame_index=self._frame_index,
            timestamp=self._frame_index / self.frame_rate,
            encode_time_ms=(time.perf_counter() - started) * 1000.0,
            width=self.width,
            height=self.height,
            chroma_width=self.chroma_width,
            chroma_height=self.chroma_height,
            motion_magnitude=motion_magnitude / 3.0,
        )

        self._frame_index += 1
        return encoded

    def reset(self) -> None:
        """Restart the sequence, forcing the next frame to be a keyframe."""
        self._frame_index = 0
        self._reference = None
        self._last_keyframe_index = -self.gop_size
        self.rate_controller.reset()


class VideoDecoder:
    """Reconstructs pictures from an RVM1 bitstream.

    Returns ``None`` when a predicted picture arrives without a usable
    reference.  That is not an error to swallow: a receiver that joins late or
    loses a key frame has to tell the sender to resend one, and the transport
    layer does exactly that when it sees a ``None``.
    """

    def __init__(self) -> None:
        self._reference: list[np.ndarray] | None = None
        self._width: int | None = None
        self._height: int | None = None
        self._luma_table: np.ndarray | None = None
        self._chroma_table: np.ndarray | None = None
        self.frames_decoded = 0
        self.keyframes_decoded = 0
        self.keyframe_requests = 0

    @property
    def has_reference(self) -> bool:
        return self._reference is not None

    def drop_reference(self) -> None:
        """Forget the reference, as if the stream had been interrupted."""
        self._reference = None

    def decode(self, frame: EncodedFrame | bytes) -> np.ndarray | None:
        """Decode one picture into an RGB image, or ``None`` if undecodable.

        Accepts either an :class:`EncodedFrame` or a bare payload, which is what
        the reassembler works with once it has rebuilt a picture from packets.
        """
        payload, is_keyframe, expected = _coerce_payload(frame)

        reader = BitReader(payload)

        if is_keyframe:
            # Only a keyframe carries the sequence header, so only a keyframe
            # starts with the magic bytes. Predicted pictures begin directly at
            # the picture header and rely on the decoder already knowing the
            # resolution and quantiser tables.
            reader.read_bits(16)
            self._read_sequence_header(reader, expected)
        else:
            if self._reference is None:
                self.keyframe_requests += 1
                return None
            if self._width != frame.width or self._height != frame.height:
                raise ValueError(
                    f"picture resolution {frame.width}x{frame.height} does not match "
                    f"the configured {self._width}x{self._height}"
                )

        assert self._luma_table is not None and self._chroma_table is not None

        is_intra = reader.read_bits(1) == _IS_INTRA
        qp = reader.read_bits(_QP_BITS) + 1

        planes: list[np.ndarray] = []
        reconstructed: list[np.ndarray] = []

        for index, (plane_width, plane_height) in enumerate(
            self._plane_dimensions()
        ):
            table = self._luma_table if index == 0 else self._chroma_table
            rows, columns = _grid(plane_width, plane_height)

            if is_intra:
                prediction = np.zeros((plane_height, plane_width), dtype=np.float64)
            else:
                field = _read_motion_field(reader, rows, columns)
                prediction = compensate(self._reference[index], field)

            levels = np.empty((rows * columns, BLOCK_SIZE, BLOCK_SIZE), dtype=np.int32)
            for block_index in range(rows * columns):
                levels[block_index] = decode_block_coefficients(reader)

            residual = _residual_from_levels(levels, table, plane_width, plane_height)
            reconstructed.append(
                np.clip(prediction + residual, 0.0, 255.0)
            )

        self._reference = reconstructed
        self.frames_decoded += 1
        if is_intra:
            self.keyframes_decoded += 1
            self._last_qp = qp

        return self._to_rgb(reconstructed)

    # -- internals -----------------------------------------------------------

    def _plane_dimensions(self) -> list[tuple[int, int]]:
        assert self._width is not None and self._height is not None
        return [
            (self._width, self._height),
            (self._width // 2, self._height // 2),
            (self._width // 2, self._height // 2),
        ]

    def _read_sequence_header(
        self, reader: BitReader, expected: tuple[int, int] | None
    ) -> None:
        version = reader.read_bits(8)
        if version != VERSION:
            raise ValueError(f"unsupported RVM version {version}")

        width = reader.read_bits(8) * BLOCK_SIZE
        height = reader.read_bits(8) * BLOCK_SIZE
        reader.read_bits(1)  # chroma format: 4:2:0

        if self._width is not None and (width, height) != (self._width, self._height):
            raise ValueError(
                f"sequence resolution {width}x{height} does not match the "
                f"configured {self._width}x{self._height}"
            )

        reader.align()
        from .entropy import read_ue

        luma_table = np.empty(64, dtype=np.int32)
        for index in range(64):
            luma_table[index] = read_ue(reader)
        chroma_table = np.empty(64, dtype=np.int32)
        for index in range(64):
            chroma_table[index] = read_ue(reader)
        reader.align()

        if expected is not None and (width, height) != expected:
            raise ValueError(
                f"sequence header resolution {width}x{height} does not match the "
                f"picture metadata {expected[0]}x{expected[1]}"
            )

        self._width = width
        self._height = height
        self._luma_table = luma_table.reshape(BLOCK_SIZE, BLOCK_SIZE)
        self._chroma_table = chroma_table.reshape(BLOCK_SIZE, BLOCK_SIZE)

    def _to_rgb(self, planes: list[np.ndarray]) -> np.ndarray:
        assert self._width is not None and self._height is not None
        luma, cb, cr = planes
        return ycbcr_to_rgb(from_planes(luma, upsample_420(cb), upsample_420(cr)))


# --------------------------------------------------------------------------
# Transform helpers shared by encoder and decoder
# --------------------------------------------------------------------------


def quantize_residual(residual: np.ndarray, table: np.ndarray) -> np.ndarray:
    """DCT then quantise a residual plane into integer coefficient blocks."""
    coefficients = dct2d_blocks(_plane_blocks(residual))
    steps = table.astype(np.float64)
    return np.rint(coefficients / steps).astype(np.int32)


def _residual_from_levels(
    levels: np.ndarray, table: np.ndarray, width: int, height: int
) -> np.ndarray:
    """Dequantise then inverse-DCT, returning the residual plane.

    Both the encoder's reconstruction branch and the decoder call this, which
    is what keeps their reference frames bit-identical.
    """
    coefficients = levels.astype(np.float64) * table.astype(np.float64)
    blocks = idct2d_blocks(coefficients)
    return _blocks_to_plane(blocks, width, height)


def _coerce_payload(
    frame: EncodedFrame | bytes,
) -> tuple[bytes, bool, tuple[int, int] | None]:
    """Normalise the argument of :meth:`VideoDecoder.decode`.

    A bare payload carries no metadata, so a sequence header at its front is
    taken as proof that it is a keyframe.  A payload with no header cannot be
    parsed at all and is rejected outright rather than being mistaken for a
    predicted picture -- silently returning ``None`` there would turn a
    corrupted stream into a mysterious keyframe request instead.
    """
    if isinstance(frame, EncodedFrame):
        return frame.data, frame.is_keyframe, (frame.width, frame.height)

    payload = bytes(frame)
    if len(payload) < 4 or not payload.startswith(MAGIC):
        raise ValueError("payload does not start with the RVM magic bytes")
    return payload, True, None


def _write_sequence_header(
    writer: BitWriter, width: int, height: int, luma_table: np.ndarray, chroma_table: np.ndarray
) -> None:
    from .entropy import write_ue

    writer.write_bits(MAGIC[0], 8)
    writer.write_bits(MAGIC[1], 8)
    writer.write_bits(VERSION, 8)
    writer.write_bits(width // BLOCK_SIZE, 8)
    writer.write_bits(height // BLOCK_SIZE, 8)
    writer.write_bits(1, 1)  # 4:2:0
    writer.byte_align()

    for table in (luma_table, chroma_table):
        for value in table.reshape(-1):
            write_ue(writer, int(value))
    writer.byte_align()


def _write_picture_header(writer: BitWriter, is_intra: bool, qp: int) -> None:
    writer.write_bits(_IS_INTRA if is_intra else _IS_INTER, 1)
    writer.write_bits(qp - 1, _QP_BITS)