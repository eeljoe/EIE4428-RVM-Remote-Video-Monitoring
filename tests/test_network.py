"""Tests for RTP-style packetisation, jitter buffering and stream statistics."""

import pytest

from rvm.network.jitter import JitterBuffer
from rvm.network.packet import (
    PAYLOAD_TYPE,
    RTP_VERSION,
    Packet,
    packetize,
    reassemble,
)
from rvm.network.stats import StreamStats


# --------------------------------------------------------------------------
# Packet header
# --------------------------------------------------------------------------


def test_packet_header_round_trips():
    packet = Packet(sequence=4321, timestamp=90000, marker=True, payload=b"hello")

    restored = Packet.parse(packet.to_bytes())

    assert restored.sequence == 4321
    assert restored.timestamp == 90000
    assert restored.marker is True
    assert restored.payload == b"hello"


def test_packet_carries_the_rtp_version():
    packet = Packet(sequence=1, timestamp=0, marker=False, payload=b"")

    assert Packet.parse(packet.to_bytes()).version == RTP_VERSION


def test_packet_carries_the_payload_type():
    packet = Packet(sequence=1, timestamp=0, marker=False, payload=b"")

    assert Packet.parse(packet.to_bytes()).payload_type == PAYLOAD_TYPE


def test_fixed_header_is_twelve_bytes():
    packet = Packet(sequence=1, timestamp=2, marker=False, payload=b"abcd")

    assert len(packet.to_bytes()) == 12 + 4


def test_sequence_numbers_wrap_at_sixteen_bits():
    packet = Packet(sequence=70000, timestamp=0, marker=False, payload=b"")

    assert Packet.parse(packet.to_bytes()).sequence == 70000 % 65536


def test_timestamp_is_carried_in_ninety_kilohertz_units():
    """90 kHz is the RTP clock, so a 25 fps picture is 3600 ticks apart."""
    packet = Packet(sequence=0, timestamp=3600, marker=False, payload=b"")

    assert Packet.parse(packet.to_bytes()).timestamp == 3600


def test_parsing_rejects_a_payload_that_is_not_rtp():
    with pytest.raises(ValueError, match="version"):
        Packet.parse(b"\x00" * 12)


def test_parsing_rejects_a_truncated_header():
    with pytest.raises(ValueError):
        Packet.parse(b"\x80")


def test_packets_compare_by_sequence_for_reordering():
    assert Packet(5, 0, False, b"") > Packet(3, 0, False, b"")


# --------------------------------------------------------------------------
# Packetisation
# --------------------------------------------------------------------------


def test_a_small_picture_fits_in_one_packet():
    packets = packetize(b"x" * 100, sequence=1, timestamp=9000)

    assert len(packets) == 1


def test_only_the_last_fragment_carries_the_marker_bit():
    packets = packetize(b"y" * 5000, sequence=1, timestamp=9000, max_payload=1000)

    assert len(packets) == 5
    assert [p.marker for p in packets] == [False, False, False, False, True]


def test_fragments_carry_consecutive_sequence_numbers():
    packets = packetize(b"y" * 2500, sequence=7, timestamp=9000, max_payload=1000)

    assert [p.sequence for p in packets] == [7, 8, 9]


def test_every_fragment_of_a_picture_shares_its_timestamp():
    packets = packetize(b"y" * 3000, sequence=1, timestamp=123456, max_payload=700)

    assert {p.timestamp for p in packets} == {123456}


def test_fragments_reassemble_into_the_original_picture():
    original = bytes(range(256)) * 12

    packets = packetize(original, sequence=40, timestamp=9000, max_payload=333)

    assert reassemble(packets) == original


def test_reassembly_across_consecutive_pictures():
    first = packetize(b"A" * 2000, sequence=1, timestamp=9000, max_payload=500)
    second = packetize(b"B" * 2000, sequence=100, timestamp=12600, max_payload=500)

    assert reassemble(first) == b"A" * 2000
    assert reassemble(second) == b"B" * 2000


def test_reassembly_returns_none_until_the_marker_arrives():
    packets = packetize(b"C" * 2000, sequence=1, timestamp=9000, max_payload=500)

    assert reassemble(packets[:-1]) is None


def test_reassembly_detects_a_fragment_gap():
    """A hole must surface as loss rather than a silently corrupt picture."""
    packets = packetize(b"D" * 2000, sequence=1, timestamp=9000, max_payload=500)

    assert reassemble(packets[:2] + packets[3:]) is None


def test_reassembly_drops_an_incomplete_picture_from_a_batch():
    packets = packetize(b"E" * 2000, sequence=1, timestamp=9000, max_payload=500)

    assert reassemble(packets[:-1]) is None


def test_an_empty_picture_produces_one_packet():
    packets = packetize(b"", sequence=1, timestamp=9000)

    assert len(packets) == 1


# --------------------------------------------------------------------------
# Jitter buffer
# --------------------------------------------------------------------------


def mk(sequence, timestamp=0, payload=b"x"):
    return Packet(sequence=sequence, timestamp=timestamp, marker=False, payload=payload)


def test_buffer_reports_nothing_before_its_playout_delay_elapses():
    buffer = JitterBuffer(playout_delay_ms=100.0)
    buffer.push(mk(0), arrival_time=0.0)

    assert buffer.pop(0.050) is None  # 50 ms in


def test_buffer_delivers_a_packet_once_its_playout_time_arrives():
    buffer = JitterBuffer(playout_delay_ms=100.0)
    buffer.push(mk(0), arrival_time=0.0)

    packet = buffer.pop(0.100)

    assert packet is not None
    assert packet.sequence == 0


def test_buffer_reorders_packets_that_arrive_out_of_order():
    buffer = JitterBuffer(playout_delay_ms=100.0)
    buffer.push(mk(2), arrival_time=0.020)
    buffer.push(mk(0), arrival_time=0.000)
    buffer.push(mk(1), arrival_time=0.010)

    # Each packet still plays out on its own schedule, so all three are
    # available only once the last one's delay has elapsed.
    assert [buffer.pop(0.30).sequence for _ in range(3)] == [0, 1, 2]
    assert buffer.out_of_order == 2


def test_buffer_does_not_deliver_a_gap_out_of_order():
    """A lost packet must stall rather than let later pictures through early."""
    buffer = JitterBuffer(playout_delay_ms=100.0)
    buffer.push(mk(0), arrival_time=0.0)
    buffer.push(mk(2), arrival_time=0.01)

    assert buffer.pop(0.10).sequence == 0
    assert buffer.pop(0.10) is None  # waiting for sequence 1


def test_buffer_counts_duplicate_arrivals_once():
    buffer = JitterBuffer(playout_delay_ms=100.0)
    buffer.push(mk(0), arrival_time=0.0)
    buffer.push(mk(0), arrival_time=0.005)

    assert buffer.duplicates == 1


def test_buffer_counts_a_lost_packet_once_the_gap_is_passed():
    buffer = JitterBuffer(playout_delay_ms=100.0)
    buffer.push(mk(0), arrival_time=0.0)
    buffer.push(mk(2), arrival_time=0.01)
    buffer.pop(0.10)
    buffer.pop(0.11)

    assert buffer.lost == 1


def test_buffer_counts_an_underflow_when_nothing_is_ready():
    buffer = JitterBuffer(playout_delay_ms=100.0)
    buffer.push(mk(0), arrival_time=0.0)
    buffer.pop(0.10)
    buffer.pop(0.11)  # nothing left

    assert buffer.underflows >= 1


def test_buffer_grows_its_delay_when_it_keeps_underflowing():
    """The lecture's regulator: buffer more when the network starves us."""
    buffer = JitterBuffer(playout_delay_ms=100.0, min_delay_ms=50.0, max_delay_ms=400.0)
    buffer.push(mk(0), arrival_time=0.0)
    buffer.pop(0.10)
    before = buffer.playout_delay_ms

    for _ in range(10):
        buffer.pop(0.11)

    assert buffer.playout_delay_ms > before


def test_buffer_shrinks_its_delay_after_a_long_clean_run():
    buffer = JitterBuffer(playout_delay_ms=300.0, min_delay_ms=50.0, max_delay_ms=400.0)
    for sequence in range(40):
        buffer.push(mk(sequence), arrival_time=sequence * 0.004)
        buffer.pop(sequence * 0.004 + 0.4)

    assert buffer.playout_delay_ms < 300.0


def test_buffer_delay_stays_within_its_configured_bounds():
    buffer = JitterBuffer(playout_delay_ms=100.0, min_delay_ms=80.0, max_delay_ms=120.0)
    for sequence in range(200):
        buffer.push(mk(sequence), arrival_time=sequence * 0.01)
        buffer.pop(sequence * 0.01 + 0.5)

    assert 80.0 <= buffer.playout_delay_ms <= 120.0


def test_buffer_never_returns_a_packet_twice():
    buffer = JitterBuffer(playout_delay_ms=50.0)
    buffer.push(mk(0), arrival_time=0.0)

    assert buffer.pop(0.05) is not None
    assert buffer.pop(0.05) is None


def test_buffer_drains_a_burst_in_order():
    buffer = JitterBuffer(playout_delay_ms=80.0)
    for sequence in range(5):
        buffer.push(mk(sequence), arrival_time=0.0)

    delivered = [buffer.pop(0.09).sequence for _ in range(5)]

    assert delivered == [0, 1, 2, 3, 4]


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------


def test_stats_start_empty():
    stats = StreamStats()

    assert stats.packets_sent == 0
    assert stats.packets_received == 0
    assert stats.bitrate == 0.0


def test_stats_count_transferred_packets_and_bits():
    stats = StreamStats()
    for index in range(10):
        stats.record_sent(mk(index, payload=b"x" * 100), now=index * 0.04)

    assert stats.packets_sent == 10
    assert stats.total_bytes == 1000


def test_stats_compute_a_bitrate_over_the_measured_window():
    stats = StreamStats(window_seconds=10.0)
    # Ten 100-byte payloads spread evenly over 0.36 s.
    for index in range(10):
        stats.record_sent(mk(index, payload=b"x" * 100), now=index * 0.04)

    assert stats.bitrate == pytest.approx(1000 / 0.36 * 8, rel=1e-6)


def test_stats_report_the_measured_frame_rate():
    stats = StreamStats()
    for index in range(25):
        stats.record_sent(
            Packet(index, index * 3600, True, b"x"), now=index * 0.04
        )  # 1.0 s, 25 pictures

    assert stats.frame_rate == pytest.approx(25.0, rel=0.05)


def test_stats_compute_the_loss_fraction():
    stats = StreamStats()
    for index in range(100):
        stats.record_sent(mk(index), now=index * 0.01)

    stats.record_received(mk(index) for index in range(90))

    assert stats.fraction_lost == pytest.approx(0.10, abs=0.02)


def test_stats_count_keyframes_separately():
    stats = StreamStats()
    stats.record_sent(Packet(0, 0, True, b"x"), now=0.0, is_keyframe=True)
    stats.record_sent(Packet(1, 3600, True, b"x"), now=0.04)

    assert stats.keyframes == 1
    assert stats.pictures == 2


def test_stats_report_a_jitter_estimate_in_milliseconds():
    stats = StreamStats()
    stats.record_sent(mk(0), now=0.0)

    # Alternating 10 ms and 40 ms transit times.
    stats.record_received(mk(0), now=0.010)
    stats.record_received(mk(1), now=0.070)

    assert stats.jitter_ms > 0.0


def test_stats_are_zero_when_nothing_has_been_sent():
    stats = StreamStats()

    assert stats.frame_rate == 0.0
    assert stats.jitter_ms == 0.0
    assert stats.fraction_lost == 0.0


def test_stats_serialise_for_the_dashboard():
    stats = StreamStats()
    stats.record_sent(mk(0, payload=b"x" * 50), now=0.0)

    snapshot = stats.snapshot()

    assert snapshot["packets_sent"] == 1
    assert snapshot["bytes"] == 50
    assert "bitrate" in snapshot and "frame_rate" in snapshot


def test_sender_reports_no_loss_before_any_feedback_arrives():
    """A sender cannot know what arrived; it must not invent a clean figure."""
    stats = StreamStats()
    for index in range(10):
        stats.record_sent(mk(index), now=index * 0.04)

    assert stats.fraction_lost == 0.0


def test_receiver_feedback_replaces_the_guessed_loss_figure():
    stats = StreamStats()
    for index in range(100):
        stats.record_sent(mk(index), now=index * 0.01)

    stats.record_feedback(received=90, lost=10)

    assert stats.fraction_lost == pytest.approx(0.10)


def test_receiver_feedback_sets_the_jitter_estimate():
    stats = StreamStats()

    stats.record_jitter_ms(27.5)

    assert stats.jitter_ms == pytest.approx(27.5)


def test_feedback_with_nothing_in_it_is_ignored():
    stats = StreamStats()

    stats.record_feedback(received=0, lost=0)

    assert stats.fraction_lost == 0.0