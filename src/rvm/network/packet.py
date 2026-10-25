"""RTP-style packetisation of coded pictures.

The receiver of a real-time stream does not get whole pictures.  It gets
datagrams that may arrive late, out of order, or not at all, and it has to
reassemble the picture from whatever turns up in time.  This module follows the
RTP fixed header (RFC 3550) closely enough to make that explicit:

===============  =========================================================
byte 0          version (2) | padding (1) | extension (1) | CSRC count (4)
byte 1          marker (1) | payload type (7)
bytes 2-3       sequence number, 16 bits, wrapping
bytes 4-7       timestamp, 90 kHz sampling clock
bytes 8-11      synchronisation source identifier
===============  =========================================================

A picture larger than the network MTU is split into fragments with
consecutive sequence numbers and a single shared timestamp, which is what lets
the receiver group them back together.  The **marker** bit is set on the final
fragment: it is the only signal that tells the receiver a picture is complete,
so a picture missing its marker is known to be incomplete rather than merely
late.

The 90 kHz clock is the conventional RTP timebase: at 25 fps one picture is
3600 ticks apart, and at 30 fps 3000.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PAYLOAD_TYPE",
    "RTP_CLOCK_HZ",
    "RTP_VERSION",
    "Packet",
    "frame_timestamp",
    "packetize",
    "reassemble",
]

RTP_VERSION = 2
PAYLOAD_TYPE = 96  # dynamic payload type, the convention for a custom codec
RTP_CLOCK_HZ = 90_000
_HEADER_BYTES = 12
_SEQUENCE_MODULUS = 1 << 16


@dataclass
class Packet:
    """One RTP packet carrying a fragment of a coded picture."""

    sequence: int
    timestamp: int
    marker: bool
    payload: bytes
    payload_type: int = PAYLOAD_TYPE
    ssrc: int = 0x52564D31  # "RVM1"
    version: int = RTP_VERSION

    def to_bytes(self) -> bytes:
        first = (self.version & 0x03) << 6
        second = (0x80 if self.marker else 0x00) | (self.payload_type & 0x7F)
        return bytes(
            [
                first,
                second,
                (self.sequence >> 8) & 0xFF,
                self.sequence & 0xFF,
            ]
        ) + self.timestamp.to_bytes(4, "big") + self.ssrc.to_bytes(
            4, "big"
        ) + self.payload

    @classmethod
    def parse(cls, data: bytes) -> "Packet":
        if len(data) < _HEADER_BYTES:
            raise ValueError(
                f"RTP packet needs at least {_HEADER_BYTES} header bytes, got {len(data)}"
            )

        version = (data[0] >> 6) & 0x03
        if version != RTP_VERSION:
            raise ValueError(f"unsupported RTP version {version}, expected {RTP_VERSION}")

        return cls(
            sequence=(data[2] << 8) | data[3],
            timestamp=int.from_bytes(data[4:8], "big"),
            marker=bool(data[1] & 0x80),
            payload_type=data[1] & 0x7F,
            ssrc=int.from_bytes(data[8:12], "big"),
            payload=data[_HEADER_BYTES:],
            version=version,
        )

    def __lt__(self, other: "Packet") -> bool:
        return self.sequence < other.sequence

    def __gt__(self, other: "Packet") -> bool:
        return self.sequence > other.sequence

    def __len__(self) -> int:
        return _HEADER_BYTES + len(self.payload)

    @property
    def size(self) -> int:
        """Bytes this packet occupies on the wire, header included."""
        return len(self)


def frame_timestamp(index: int, frame_rate: float) -> int:
    """Convert a frame index into a 90 kHz RTP timestamp."""
    if frame_rate <= 0:
        raise ValueError(f"frame_rate must be positive, got {frame_rate}")
    return int(round(index * RTP_CLOCK_HZ / frame_rate))


def packetize(
    picture: bytes,
    sequence: int,
    timestamp: int,
    max_payload: int = 1200,
    ssrc: int = 0x52564D31,
) -> list[Packet]:
    """Split a coded picture into RTP-sized fragments.

    ``max_payload`` should sit below the path MTU so the IP, UDP and link
    headers still fit; 1200 bytes leaves comfortable room.
    """
    if max_payload <= 0:
        raise ValueError(f"max_payload must be positive, got {max_payload}")

    if len(picture) <= max_payload:
        return [
            Packet(
                sequence=sequence % _SEQUENCE_MODULUS,
                timestamp=timestamp,
                marker=True,
                payload=picture,
                ssrc=ssrc,
            )
        ]

    packets: list[Packet] = []
    offset = 0
    fragment_index = 0

    while offset < len(picture):
        chunk = picture[offset : offset + max_payload]
        offset += max_payload
        is_last = offset >= len(picture)

        packets.append(
            Packet(
                sequence=(sequence + fragment_index) % _SEQUENCE_MODULUS,
                timestamp=timestamp,
                marker=is_last,
                payload=chunk,
                ssrc=ssrc,
            )
        )
        fragment_index += 1

    return packets


def reassemble(packets: list[Packet]) -> bytes | None:
    """Rebuild a picture from its fragments.

    Returns ``None`` unless every fragment of exactly one picture is present,
    in sequence.  A missing fragment is reported as incompletion rather than
    being papered over, because a partially reassembled picture would decode
    into garbage that looks like a codec bug.
    """
    if not packets:
        return None

    timestamp = packets[0].timestamp
    if any(packet.timestamp != timestamp for packet in packets):
        return None

    sequences = [packet.sequence for packet in packets]
    if sequences != list(range(sequences[0], sequences[0] + len(sequences))):
        return None

    if not packets[-1].marker:
        return None

    return b"".join(packet.payload for packet in packets)