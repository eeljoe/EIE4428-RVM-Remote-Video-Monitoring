"""Encoder rate control: virtual buffer, GOP allocation and QP limiting.

Rate control answers the second of the two questions the course poses about
rate: the network side decides *how much* rate is available (congestion control,
feedback over RTCP), and the encoder side decides *how to produce that rate*
(this module).  The encoder cannot simply hold QP fixed: with a fixed
quantiser the bit rate swings with scene complexity, and with a fixed bit rate
the quality swings.  A live monitoring stream needs the bit rate to stay inside
a budget that the network sets.

The approach is TM5's **virtual buffer**: imagine a decoder buffer of known
capacity that drains at exactly the demanded rate.  Whatever the encoder
produces, the buffer level changes by

    fullness change = bits produced - bits removed (at the demanded rate)

and the quantiser parameter is derived from that level:

    Q_j = (d_j / r) * 31        with    r = (2 * bit_rate) / picture_rate

A full buffer therefore raises QP, which coarsens the quantiser and sheds
bits -- closing the loop.  Two practical refinements from H.264 are layered on
top: QP is started from the demanded bits per pixel rather than a constant, and
the change in QP between consecutive pictures is limited, because a quantiser
that swings violently is visible to the user even when the average rate is on
target.

One honest limitation of every scheme in this family is carried over from
TM5: the complexity estimate lags by a picture, so a sudden scene change
(a person walking into view) is mis-predicted and the error then propagates
through the pictures that follow.
"""

from __future__ import annotations

from enum import Enum

import numpy as np

__all__ = [
    "BITS_PER_MB_ESTIMATE",
    "FrameType",
    "QP_LIMIT",
    "RateController",
    "allocate_gop_bits",
    "bits_per_pixel",
    "block_activity",
    "initial_complexity",
    "initial_qp_from_bpp",
    "normalize_activity",
]

class FrameType(Enum):
    """The coding mode of a picture."""

    I = "I"
    P = "P"
    B = "B"


# TM5: QP must not move by more than this many steps between pictures.
QP_LIMIT = 2

# TM5 complexity weights for GOP bit allocation: I : P : B = 4 : 2 : 1.
_COMPLEXITY_WEIGHT = {FrameType.I: 4.0, FrameType.P: 2.0, FrameType.B: 1.0}

# TM5 constants for the initial complexity estimates (bit_rate in bits/s).
_INITIAL_COMPLEXITY_FACTOR = {
    FrameType.I: 160.0 / 115.0,
    FrameType.P: 60.0 / 115.0,
    FrameType.B: 42.0 / 115.0,
}

# H.264 initial-QP coefficients, for QCIF/CIF and for larger frames.
_QP_COEFFS_SMALL = (0.15, 0.45, 0.9)
_QP_COEFFS_LARGE = (0.6, 1.4, 2.4)

# CIF is 352x288; anything larger uses the second coefficient set.
_CIF_AREA = 352 * 288

# Rough planning figure for how many bits one macroblock is expected to cost.
BITS_PER_MB_ESTIMATE = 1600

# Used when the bits-per-pixel model lands outside the legal QP range, which it
# does for almost every realistic parameter set: the coefficients assume a
# normalisation that a plain bits-per-pixel input rarely satisfies. Starting
# mid-range lets the virtual buffer converge within about a dozen pictures,
# while starting at either extreme risks a badly wrong first picture.
DEFAULT_START_QP = 26


def bits_per_pixel(
    target_bitrate: float, frame_rate: float, width: int, height: int
) -> float:
    """Demanded bits per pixel: ``bitrate / (fps * height * width)``."""
    if frame_rate <= 0 or width <= 0 or height <= 0:
        raise ValueError("frame rate and dimensions must be positive")
    return target_bitrate / (frame_rate * height * width)


def initial_qp_from_bpp(
    bpp: float, larger_than_cif: bool, clamp: bool = True
) -> float:
    """H.264 starting QP from the demanded bits per pixel.

    A three-segment model: a near-linear segment for very low rates, a steeper
    middle segment, and a saturating high-rate segment::

        QP = l1 * bpp   if bpp <= l2
        QP = l2 * bpp   if l3 <= bpp <= l2
        QP = l3 * bpp   if bpp > l3

    The raw result is often far below 1 because the coefficients assume a
    starting point that the virtual buffer will immediately pull back to a
    usable level.  With ``clamp=True`` the value is constrained to the legal
    QP range, so a conservative sequence simply starts at its finest setting
    and lets buffer feedback coarsen it -- the safe direction, since starting
    coarse would overflow the buffer before the first feedback arrives.
    """
    l1, l2, l3 = _QP_COEFFS_LARGE if larger_than_cif else _QP_COEFFS_SMALL

    if bpp <= l2:
        qp = l1 * bpp
    elif bpp <= l3:
        qp = l2 * bpp
    else:
        qp = l3 * bpp

    if not clamp:
        return float(qp)
    return float(min(51, max(1, qp)))


def allocate_gop_bits(
    total_bits: float, counts: dict[FrameType, int]
) -> dict[FrameType, float]:
    """Split a GOP bit budget across picture types by TM5 complexity weight.

    ``I : P : B = 4 : 2 : 1`` because intra pictures carry all their energy,
    predicted pictures only the residual, and bi-directional pictures the least.
    """
    weights = {
        frame_type: _COMPLEXITY_WEIGHT[frame_type] * count
        for frame_type, count in counts.items()
        if count > 0
    }

    denominator = sum(weights.values())
    if denominator <= 0:
        return {}

    return {
        frame_type: total_bits * weight / denominator
        for frame_type, weight in weights.items()
    }


def initial_complexity(frame_type: FrameType, bit_rate: float) -> float:
    """TM5 initial complexity estimate for a picture type."""
    return _INITIAL_COMPLEXITY_FACTOR[frame_type] * bit_rate


def block_activity(variances: list[float] | np.ndarray) -> float:
    """TM5 spatial activity of a macroblock: ``Act = 1 + min(vblk_1 .. vblk_8)``.

    The ``+ 1`` is a floor, not cosmetics: it keeps a completely flat block at
    a non-zero activity so the normalisation below can never divide by zero or
    produce a degenerate quantiser.
    """
    values = np.asarray(variances, dtype=np.float64)
    if values.size == 0:
        raise ValueError("block_activity needs at least one variance")
    return float(1.0 + values.min())


def normalize_activity(activity: float, average_activity: float) -> float:
    """TM5 step 3: map block activity onto a quantiser multiplier.

    Blocks busier than the running picture average are quantised more coarsely
    and flat blocks more finely, so the bits are spread over the picture rather
    than consumed by whichever region is busiest.  The three properties the
    controller relies on are that the multiplier is exactly 1 at the average,
    above 1 above the average, and below 1 below it::

        N_act = (2 * Act + avg_act) / (2 * avg_act + Act)
    """
    if average_activity <= 0:
        return 1.0
    return float((2.0 * activity + average_activity) / (2.0 * average_activity + activity))


class RateController:
    """Virtual-buffer rate controller driving a per-picture QP.

    The controller is told how many bits each encoded picture actually consumed;
    it keeps a simulated decoder buffer in step and converts the buffer level
    into the next quantiser parameter.
    """

    def __init__(
        self,
        target_bitrate: int,
        frame_rate: float,
        width: int,
        height: int,
        qp_min: int = 1,
        qp_max: int = 51,
        qp_limit: int = QP_LIMIT,
        buffer_seconds: float = 1.0,
    ) -> None:
        if target_bitrate <= 0:
            raise ValueError(f"target_bitrate must be positive, got {target_bitrate}")
        if frame_rate <= 0:
            raise ValueError(f"frame_rate must be positive, got {frame_rate}")
        if qp_min > qp_max:
            raise ValueError(f"empty QP window: {qp_min} > {qp_max}")

        self.target_bitrate = int(target_bitrate)
        self.frame_rate = float(frame_rate)
        self.width = int(width)
        self.height = int(height)
        self.qp_min = int(qp_min)
        self.qp_max = int(qp_max)
        self.qp_limit = int(qp_limit)

        self.bits_per_frame = self.target_bitrate / self.frame_rate
        self.buffer_capacity = float(self.bits_per_frame * frame_rate * buffer_seconds)

        self._larger_than_cif = (self.width * self.height) > _CIF_AREA
        raw_qp = initial_qp_from_bpp(
            bits_per_pixel(target_bitrate, frame_rate, width, height),
            larger_than_cif=self._larger_than_cif,
            clamp=False,
        )
        # Keep the model's answer when it is usable; otherwise start mid-range
        # and let the buffer walk it to the right operating point.
        self._initial_qp = (
            self._clamp_qp(raw_qp) if 1.0 <= raw_qp <= 51.0 else DEFAULT_START_QP
        )

        self._initial_fullness = self.reaction_parameter * 10.0 / 31.0
        self._fullness = min(self.buffer_capacity, max(0.0, self._initial_fullness))
        self._qp = self._initial_qp
        self._total_bits_out = 0
        self._frames_out = 0

    # -- static configuration ------------------------------------------------

    @property
    def reaction_parameter(self) -> float:
        """TM5 reaction parameter ``r = (2 * bit_rate) / picture_rate``."""
        return (2.0 * self.target_bitrate) / self.frame_rate

    @property
    def initial_qp(self) -> int:
        return self._initial_qp

    @property
    def initial_fullness(self) -> float:
        return self._initial_fullness

    @property
    def buffer_capacity(self) -> float:
        return self._buffer_capacity

    @buffer_capacity.setter
    def buffer_capacity(self, value: float) -> None:
        self._buffer_capacity = max(1.0, float(value))

    @property
    def buffer_fullness(self) -> float:
        """Current virtual buffer level, in bits."""
        return self._fullness

    @property
    def buffer_level(self) -> float:
        """Buffer fullness expressed as a multiple of ``r`` (0.0 to 1.0)."""
        return self._fullness / self.reaction_parameter

    @property
    def current_qp(self) -> int:
        return self._qp

    @property
    def total_bits_out(self) -> int:
        return self._total_bits_out

    @property
    def frames_encoded(self) -> int:
        return self._frames_out

    @property
    def average_bitrate(self) -> float:
        """Bits per second actually produced so far."""
        if self._frames_out == 0:
            return 0.0
        seconds = self._frames_out / self.frame_rate
        return self._total_bits_out / seconds

    # -- control ------------------------------------------------------------

    def qp_for_buffer_level(self, level: float) -> float:
        """TM5 ``Q_j = (d_j / r) * 31`` for a buffer level given in multiples of ``r``."""
        return level * 31.0

    def _clamp_qp(self, qp: float) -> int:
        return int(min(self.qp_max, max(self.qp_min, round(qp))))

    def _limit_qp_step(self, previous: int, proposed: int) -> int:
        """Apply the H.264 QP limiter: move at most ``qp_limit`` per picture."""
        lower = previous - self.qp_limit
        upper = previous + self.qp_limit
        return int(min(upper, max(lower, proposed)))

    def next_qp(self) -> int:
        """The QP to use for the next picture, without advancing the controller."""
        return self._qp

    def update(self, bits_used: int, frame_type: FrameType = FrameType.P) -> int:
        """Feed back the actual size of an encoded picture and get the next QP.

        The buffer drains at the demanded rate whatever the encoder produced,
        so a picture that overran its budget leaves the buffer fuller and pushes
        the next QP up.
        """
        if bits_used < 0:
            raise ValueError(f"bits_used must be non-negative, got {bits_used}")

        self._fullness += bits_used - self.bits_per_frame
        self._fullness = min(
            self.buffer_capacity, max(0.0, self._fullness)
        )

        self._total_bits_out += int(bits_used)
        self._frames_out += 1

        level = self.buffer_level
        proposed = self._clamp_qp(self.qp_for_buffer_level(level))
        self._qp = self._limit_qp_step(self._qp, proposed)
        return self._qp

    def reset(self) -> None:
        """Return the controller to its start-of-sequence state."""
        self._fullness = min(self.buffer_capacity, max(0.0, self._initial_fullness))
        self._qp = self._initial_qp
        self._total_bits_out = 0
        self._frames_out = 0