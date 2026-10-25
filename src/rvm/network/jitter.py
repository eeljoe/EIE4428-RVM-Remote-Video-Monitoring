"""Client-side jitter buffer.

Packets that leave the server at a steady cadence arrive spread out by the
network: some are delayed by a congested queue, some overtake each other, some
never arrive.  A receiver that displayed each packet the instant it landed would
produce a visibly irregular picture.

The playout buffer is the regulator the course describes.  Each packet is held
until its *playout time* -- its send time plus the configured delay -- so that
ordinary variation is absorbed.  That delay is the whole design trade-off:

* too small and the buffer **underflows**, playback pauses, and the lecture is
  explicit that underflow causes jerkiness and a sharp fall in perceived
  quality;
* too large and the buffer **overflows**, or simply adds latency the viewer
  feels as sluggishness.

So the delay adapts: it grows after an underflow and relaxes back down during a
long clean run, staying inside configured bounds.  That trades latency for
continuity only as far as the network actually requires.

A gap is never skipped silently.  When the expected sequence number is missing
the buffer stalls, because a live stream cannot afford to display a stale
picture in place of the current one; the loss is counted and the transport
layer decides what to do about it.
"""

from __future__ import annotations

from .packet import Packet

__all__ = ["JitterBuffer"]

_GROW_STEP_MS = 25.0
_SHRINK_STEP_MS = 5.0
_CLEAN_RUNS_BEFORE_SHRINKING = 20


class JitterBuffer:
    """Reorders packets and releases them on a smoothed playout schedule."""

    def __init__(
        self,
        playout_delay_ms: float = 120.0,
        min_delay_ms: float = 40.0,
        max_delay_ms: float = 500.0,
        capacity: int = 1024,
    ) -> None:
        if min_delay_ms > max_delay_ms:
            raise ValueError(
                f"empty delay window: min {min_delay_ms} > max {max_delay_ms}"
            )

        self._initial_delay_ms = playout_delay_ms
        self._min_delay_ms = min_delay_ms
        self._max_delay_ms = max_delay_ms
        self._capacity = capacity

        self._delay_ms = min(max(playout_delay_ms, min_delay_ms), max_delay_ms)
        self._pending: dict[int, Packet] = {}
        self._send_times: dict[int, float] = {}
        self._next_sequence: int | None = None
        self._gap_reported: int | None = None
        self._released_anything = False

        self.received = 0
        self.duplicates = 0
        self.out_of_order = 0
        self.lost = 0
        self.underflows = 0
        self._clean_run = 0

    # -- state ---------------------------------------------------------------

    @property
    def playout_delay_ms(self) -> float:
        return self._delay_ms

    @property
    def pending(self) -> int:
        return len(self._pending)

    @property
    def last_lost_sequence(self) -> int | None:
        """The sequence number of the gap currently being waited on, if any."""
        return self._gap_reported

    # -- ingest --------------------------------------------------------------

    def push(self, packet: Packet, arrival_time: float) -> bool:
        """Offer an arriving packet to the buffer.

        ``arrival_time`` is in seconds.  Returns ``True`` if the packet was
        newly accepted and ``False`` if it was a duplicate.
        """
        if packet.sequence in self._pending:
            self.duplicates += 1
            return False

        if self._next_sequence is None:
            self._next_sequence = packet.sequence
        elif packet.sequence != self._next_sequence:
            # Anything that is not the expected packet is either out of order
            # or has overtaken a gap; both are worth knowing about.
            self.out_of_order += 1
            self._clean_run = 0

        if not self._released_anything:
            # Nothing has played out yet, so the starting point is still open:
            # if an earlier packet turns up late it becomes the start instead.
            self._next_sequence = min(self._next_sequence, packet.sequence)

        self._pending[packet.sequence] = packet
        self._send_times[packet.sequence] = arrival_time
        self.received += 1

        if len(self._pending) > self._capacity:
            self._evict_oldest()

        return True

    def _evict_oldest(self) -> None:
        """Drop the furthest-ahead packet; the buffer is never allowed to grow."""
        if not self._pending:
            return
        furthest = max(self._pending)
        self._pending.pop(furthest, None)
        self._send_times.pop(furthest, None)

    # -- playout -------------------------------------------------------------

    def pop(self, now: float) -> Packet | None:
        """Release the next in-order packet if its playout time has arrived."""
        if self._next_sequence is None:
            self.underflows += 1
            self._grow()
            return None

        wanted = self._next_sequence
        packet = self._pending.get(wanted)

        if packet is None:
            # The expected packet never arrived. Count the gap once, then wait
            # for it: skipping ahead would show a stale picture as current.
            if self._gap_reported != wanted:
                self._gap_reported = wanted
                self.lost += 1
            self.underflows += 1
            self._grow()
            return None

        send_time = self._send_times.get(wanted, now)
        if now < send_time + self._delay_ms / 1000.0:
            self._clean_run = 0
            return None

        self._pending.pop(wanted, None)
        self._send_times.pop(wanted, None)
        self._next_sequence = wanted + 1
        self._released_anything = True

        if packet.marker:
            self._gap_reported = None
        self._clean_run += 1
        if self._clean_run >= _CLEAN_RUNS_BEFORE_SHRINKING:
            self._shrink()

        return packet

    def drain(self, now: float) -> list[Packet]:
        """Release every packet that is ready to be displayed."""
        released: list[Packet] = []
        while True:
            packet = self.pop(now)
            if packet is None:
                break
            released.append(packet)
        return released

    def resynchronise(self, sequence: int) -> None:
        """Jump to a new starting point, discarding the backlog.

        Used after a stream interruption, when waiting for a gap that will
        never be filled would stall playback for good.
        """
        self._pending.clear()
        self._send_times.clear()
        self._next_sequence = sequence
        self._gap_reported = None
        self._released_anything = True

    def reset(self) -> None:
        """Return to the configured starting state."""
        self._pending.clear()
        self._send_times.clear()
        self._next_sequence = None
        self._gap_reported = None
        self._released_anything = False
        self._delay_ms = min(
            max(self._initial_delay_ms, self._min_delay_ms), self._max_delay_ms
        )
        self._clean_run = 0

    # -- adaptive delay ------------------------------------------------------

    def _grow(self) -> None:
        self._delay_ms = min(self._max_delay_ms, self._delay_ms + _GROW_STEP_MS)

    def _shrink(self) -> None:
        if self._delay_ms > self._min_delay_ms:
            self._delay_ms = max(self._min_delay_ms, self._delay_ms - _SHRINK_STEP_MS)
        self._clean_run = 0