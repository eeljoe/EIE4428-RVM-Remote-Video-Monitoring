"""RTCP-style delivery statistics for the dashboard and for rate adaptation.

The lecture notes that rate control needs feedback from the receiver, and that
feedback is what RTCP carries.  These statistics are that feedback: what was
sent, what arrived, how much was lost, and how much the arrival times wandered.

The jitter estimate follows the RFC 3550 definition rather than a sample
standard deviation, because it is a *smoothed* deviation of inter-arrival time
that deliberately ignores out-of-order arrivals::

    J = J + (|D(i-1, i)| - J) / 16

That smoothing is what makes it usable as a live control signal rather than a
number that swings with every hiccup.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from .packet import Packet

__all__ = ["StreamStats"]

_JITTER_SMOOTHING = 16.0


@dataclass
class StreamStats:
    """Counters and derived rates for one direction of a stream."""

    window_seconds: float = 2.0

    packets_sent: int = 0
    packets_received: int = 0
    total_bytes: int = 0
    pictures: int = 0
    keyframes: int = 0

    _window: deque = field(default_factory=deque, repr=False)
    _first_sent_at: float | None = field(default=None, repr=False)
    _last_sent_at: float | None = field(default=None, repr=False)
    _last_arrival: float | None = field(default=None, repr=False)
    _jitter: float = field(default=0.0, repr=False)
    _feedback_received: int = 0
    _feedback_lost: int = 0
    _feedback_total: int = 0
    _reported_jitter_ms: float = 0.0

    # -- recording -----------------------------------------------------------

    def record_sent(self, packet: Packet, now: float, is_keyframe: bool = False) -> None:
        """Note a packet leaving the server."""
        self.packets_sent += 1
        size = len(packet.payload)
        self.total_bytes += size

        if self._first_sent_at is None:
            self._first_sent_at = now
        self._last_sent_at = now

        self._window.append((now, size))
        cutoff = now - self.window_seconds
        while len(self._window) > 1 and self._window[0][0] < cutoff:
            self._window.popleft()

        # The marker bit terminates a picture, which is how the receiver knows
        # that picture is complete.  A key frame is counted once, on the
        # fragment that carries the marker, rather than once per fragment it
        # was split into -- otherwise a large intra picture is counted as
        # several key frames and the figure is meaningless.
        if packet.marker:
            self.pictures += 1
            if is_keyframe:
                self.keyframes += 1

    def record_received(
        self,
        packets: Packet | Iterable[Packet] | None = None,
        now: float = 0.0,
    ) -> None:
        """Note packets arriving at the client and update the jitter estimate."""
        if packets is None:
            return

        arrivals = (
            [(packets, now)]
            if isinstance(packets, Packet)
            else [(packet, now) for packet in packets]
        )

        for packet, arrival in arrivals:
            self.packets_received += 1

            if self._last_arrival is None:
                self._last_arrival = arrival
                continue

            interarrival = arrival - self._last_arrival
            self._last_arrival = arrival
            if interarrival < 0:
                continue  # reordered arrivals are deliberately ignored

            self._jitter += (abs(interarrival) - self._jitter) / _JITTER_SMOOTHING

    def record_feedback(self, received: int, lost: int) -> None:
        """Adopt delivery figures reported by a receiver.

        A sender knows what it sent but not what arrived, so loss is only
        meaningful once a client reports back. Until then the server has no
        loss figure to publish rather than a fabricated one.
        """
        total = max(0, received) + max(0, lost)
        if total <= 0:
            return
        self._feedback_received = max(0, received)
        self._feedback_lost = max(0, lost)
        self._feedback_total = total

    def record_jitter_ms(self, jitter_ms: float) -> None:
        """Adopt a receiver's jitter estimate, in milliseconds."""
        self._reported_jitter_ms = max(0.0, float(jitter_ms))

    # -- derived -------------------------------------------------------------

    @property
    def bitrate(self) -> float:
        """Payload bits per second across the trailing window.

        Measured over the payload rather than the whole datagram: the RTP
        header overhead is a constant few percent and the number the viewer
        cares about is the video rate.
        """
        if len(self._window) < 2:
            return 0.0

        span = self._window[-1][0] - self._window[0][0]
        if span <= 0:
            return 0.0

        total = sum(size for _, size in self._window)
        return (total / span) * 8.0

    @property
    def frame_rate(self) -> float:
        """Pictures per second measured since the first transmission."""
        if (
            self.pictures == 0
            or self._first_sent_at is None
            or self._last_sent_at is None
        ):
            return 0.0

        span = self._last_sent_at - self._first_sent_at
        if span <= 0:
            return 0.0
        return self.pictures / span

    @property
    def fraction_lost(self) -> float:
        """Share of packets that never arrived.

        Uses receiver feedback once a client has reported. Without feedback
        the honest answer is "not known yet", reported as zero rather than a
        fabricated figure that would make the dashboard claim a clean
        network on a link nobody has measured. The local receive counter is
        only meaningful when this object is used at the receiving end, so a
        sender must not infer loss from its own zero.
        """
        if self._feedback_total > 0:
            return max(0.0, self._feedback_lost / self._feedback_total)

        if self.packets_received <= 0:
            return 0.0

        expected = max(self.packets_sent, self.packets_received)
        if expected == 0:
            return 0.0
        return max(0.0, (self.packets_sent - self.packets_received) / expected)

    @property
    def jitter_ms(self) -> float:
        """Smoothed inter-arrival variation, in milliseconds.

        A receiver's own estimate is preferred once one has been reported,
        because the sender cannot measure what happens after its packets
        leave.
        """
        if self._reported_jitter_ms > 0.0:
            return self._reported_jitter_ms
        return self._jitter * 1000.0

    def snapshot(self) -> dict[str, float]:
        """A JSON-friendly view for the live dashboard."""
        return {
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes": self.total_bytes,
            "pictures": self.pictures,
            "keyframes": self.keyframes,
            "bitrate": round(self.bitrate, 1),
            "frame_rate": round(self.frame_rate, 2),
            "fraction_lost": round(self.fraction_lost, 4),
            "jitter_ms": round(self.jitter_ms, 3),
        }

    def reset(self) -> None:
        self.packets_sent = 0
        self.packets_received = 0
        self.total_bytes = 0
        self.pictures = 0
        self.keyframes = 0
        self._window.clear()
        self._first_sent_at = None
        self._last_sent_at = None
        self._last_arrival = None
        self._jitter = 0.0
        self._feedback_received = 0
        self._feedback_lost = 0
        self._feedback_total = 0
        self._reported_jitter_ms = 0.0