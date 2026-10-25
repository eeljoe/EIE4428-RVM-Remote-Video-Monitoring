"""Tests for encoder rate control: virtual buffer, GOP allocation, QP limiting."""

import pytest

from rvm.codec.ratecontrol import (
    BITS_PER_MB_ESTIMATE,
    FrameType,
    QP_LIMIT,
    RateController,
    allocate_gop_bits,
    bits_per_pixel,
    block_activity,
    initial_complexity,
    initial_qp_from_bpp,
    normalize_activity,
)


# --------------------------------------------------------------------------
# Demanded bits per pixel and the H.264 starting QP
# --------------------------------------------------------------------------


def test_bits_per_pixel_divides_the_rate_by_the_frame_size():
    # 500 kbps, 25 fps, 352x288 -> 500000 / (25 * 352 * 288)
    bpp = bits_per_pixel(500_000, 25, 352, 288)

    assert bpp == pytest.approx(500_000 / (25 * 352 * 288))


def test_initial_qp_for_cif_follows_the_three_segment_model():
    # CIF coefficients l1=0.15, l2=0.45, l3=0.9 (lecture 04).
    bpp = 0.30  # bpp <= l2 -> QP = l1 * bpp

    raw = initial_qp_from_bpp(bpp, larger_than_cif=False, clamp=False)
    assert raw == pytest.approx(0.15 * bpp)


def test_initial_qp_mid_segment_uses_the_second_slope():
    bpp = 0.60  # l2 < bpp <= l3 -> QP = l2 * bpp

    raw = initial_qp_from_bpp(bpp, larger_than_cif=False, clamp=False)
    assert raw == pytest.approx(0.45 * bpp)


def test_initial_qp_high_segment_uses_the_third_slope():
    bpp = 1.20  # bpp > l3 -> QP = l3 * bpp

    raw = initial_qp_from_bpp(bpp, larger_than_cif=False, clamp=False)
    assert raw == pytest.approx(0.9 * bpp)


def test_initial_qp_uses_the_larger_coefficients_for_big_frames():
    bpp = 0.30

    raw = initial_qp_from_bpp(bpp, larger_than_cif=True, clamp=False)
    assert raw == pytest.approx(0.6 * bpp)


def test_initial_qp_is_a_monotonic_function_of_demanded_bpp():
    values = [0.01 * i for i in range(1, 30)]
    qps = [initial_qp_from_bpp(v, larger_than_cif=False) for v in values]

    assert qps == sorted(qps)


def test_initial_qp_is_clamped_into_the_legal_range():
    assert initial_qp_from_bpp(0.0001, larger_than_cif=False) >= 1
    assert initial_qp_from_bpp(50.0, larger_than_cif=True) <= 51


# --------------------------------------------------------------------------
# GOP bit allocation (TM5 complexity ratio I:P:B = 4:2:1)
# --------------------------------------------------------------------------


def test_gop_allocation_follows_the_lecture_worked_example():
    """20000 bits with one I, one P and two B gives the I frame 10000 bits."""
    shares = allocate_gop_bits(20_000, {FrameType.I: 1, FrameType.P: 1, FrameType.B: 2})

    assert shares[FrameType.I] == pytest.approx(10_000)


def test_gop_allocation_is_zero_for_absent_picture_types():
    shares = allocate_gop_bits(20_000, {FrameType.I: 1, FrameType.P: 1, FrameType.B: 0})

    assert FrameType.B not in shares or shares[FrameType.B] == 0


def test_gop_allocation_sums_to_the_available_budget():
    counts = {FrameType.I: 1, FrameType.P: 3, FrameType.B: 2}
    budget = 40_000

    shares = allocate_gop_bits(budget, counts)

    assert sum(shares.values()) == pytest.approx(budget)


def test_gop_allocation_gives_b_frames_less_than_p_frames():
    shares = allocate_gop_bits(40_000, {FrameType.I: 1, FrameType.P: 1, FrameType.B: 1})

    assert shares[FrameType.I] > shares[FrameType.P] > shares[FrameType.B]


def test_initial_complexity_uses_the_lecture_constants():
    bitrate = 500_000

    assert initial_complexity(FrameType.I, bitrate) == pytest.approx(
        160 * bitrate / 115
    )
    assert initial_complexity(FrameType.P, bitrate) == pytest.approx(
        60 * bitrate / 115
    )
    assert initial_complexity(FrameType.B, bitrate) == pytest.approx(
        42 * bitrate / 115
    )


# --------------------------------------------------------------------------
# Virtual buffer controller
# --------------------------------------------------------------------------


def test_controller_budget_per_frame_is_the_rate_divided_by_the_frame_rate():
    controller = RateController(
        target_bitrate=500_000, frame_rate=25, width=352, height=288
    )

    assert controller.bits_per_frame == pytest.approx(20_000)


def test_reaction_parameter_matches_the_tm5_definition():
    """r = (2 * bit_rate) / picture_rate."""
    controller = RateController(
        target_bitrate=500_000, frame_rate=25, width=352, height=288
    )

    assert controller.reaction_parameter == pytest.approx((2 * 500_000) / 25)


def test_qp_rises_with_buffer_fullness():
    """A fuller buffer must coarsen the quantiser to shed rate."""
    controller = RateController(
        target_bitrate=500_000, frame_rate=25, width=352, height=288
    )

    low = controller.qp_for_buffer_level(1.0)
    high = controller.qp_for_buffer_level(2.0)

    assert high > low


def test_initial_qp_is_within_a_few_steps_of_the_bpp_estimate():
    controller = RateController(
        target_bitrate=500_000, frame_rate=25, width=352, height=288
    )

    assert abs(controller.current_qp - controller.initial_qp) <= QP_LIMIT


def test_overspending_raises_the_next_qp():
    controller = RateController(
        target_bitrate=100_000, frame_rate=25, width=352, height=288
    )
    before = controller.current_qp

    controller.update(bits_used=200_000, frame_type=FrameType.P)

    assert controller.current_qp >= before


def test_underspending_lowers_the_next_qp():
    controller = RateController(
        target_bitrate=1_000_000, frame_rate=25, width=352, height=288
    )
    controller.update(bits_used=0, frame_type=FrameType.P)  # drain first
    before = controller.current_qp

    for _ in range(4):
        controller.update(bits_used=0, frame_type=FrameType.P)

    assert controller.current_qp <= before


def test_qp_change_is_limited_between_consecutive_pictures():
    """H.264 practice: QP must not swing by more than +/-2 per picture."""
    controller = RateController(
        target_bitrate=200_000, frame_rate=25, width=352, height=288
    )

    previous = controller.current_qp
    for _ in range(25):
        controller.update(bits_used=500_000, frame_type=FrameType.P)  # heavy overspend
        assert abs(controller.current_qp - previous) <= QP_LIMIT
        previous = controller.current_qp


def test_qp_never_leaves_the_legal_range():
    controller = RateController(
        target_bitrate=10_000, frame_rate=25, width=352, height=288
    )

    for _ in range(200):
        controller.update(bits_used=10_000_000, frame_type=FrameType.P)

    assert 1 <= controller.current_qp <= 51


def test_buffer_fullness_is_clamped_at_capacity():
    controller = RateController(
        target_bitrate=100_000, frame_rate=25, width=352, height=288
    )

    for _ in range(100):
        controller.update(bits_used=10_000_000, frame_type=FrameType.P)

    assert controller.buffer_fullness <= controller.buffer_capacity


def test_buffer_fullness_never_goes_negative():
    controller = RateController(
        target_bitrate=1_000_000, frame_rate=25, width=352, height=288
    )

    for _ in range(100):
        controller.update(bits_used=0, frame_type=FrameType.P)

    assert controller.buffer_fullness >= 0


def test_controller_tracks_the_bits_it_has_produced():
    controller = RateController(
        target_bitrate=100_000, frame_rate=25, width=352, height=288
    )

    for _ in range(10):
        controller.update(bits_used=4_000, frame_type=FrameType.P)

    assert controller.total_bits_out == 40_000


def test_controller_reports_an_average_bitrate():
    controller = RateController(
        target_bitrate=100_000, frame_rate=25, width=352, height=288
    )

    for _ in range(10):
        controller.update(bits_used=4_000, frame_type=FrameType.P)

    # 10 frames at 25 fps = 0.4 s carrying 40000 bits = 100 kbps
    assert controller.average_bitrate == pytest.approx(100_000)


def test_reset_returns_the_controller_to_its_starting_point():
    controller = RateController(
        target_bitrate=100_000, frame_rate=25, width=352, height=288
    )
    controller.update(bits_used=900_000, frame_type=FrameType.P)

    controller.reset()

    assert controller.total_bits_out == 0
    assert controller.current_qp == controller.initial_qp
    assert controller.buffer_fullness == pytest.approx(controller.initial_fullness)


# --------------------------------------------------------------------------
# Activity-adaptive quantisation (TM5 step 3)
# --------------------------------------------------------------------------


def test_block_activity_never_reaches_zero():
    """The +1 floor in Act = 1 + min(vblk) keeps the normalisation well posed."""
    assert block_activity([0.0] * 8) == pytest.approx(1.0)


def test_block_activity_takes_the_smallest_sub_block_variance():
    assert block_activity([50.0, 10.0, 90.0, 30.0]) == pytest.approx(11.0)


def test_activity_above_the_average_scales_up_the_quantiser():
    """A busy macroblock gets a larger step so the bit budget is shared evenly."""
    assert normalize_activity(800.0, 100.0) > 1.0


def test_activity_below_the_average_scales_the_quantiser_down():
    assert normalize_activity(20.0, 100.0) < 1.0


def test_activity_normalisation_is_unity_at_the_average():
    assert normalize_activity(100.0, 100.0) == pytest.approx(1.0)


def test_activity_multiplier_stays_positive_for_a_dead_block():
    assert 0.0 < normalize_activity(0.0, 100.0) < 1.0


def test_activity_multiplier_is_bounded_for_extreme_activity():
    assert normalize_activity(1e9, 1.0) <= 2.0


def test_bits_per_macroblock_estimate_is_positive():
    assert BITS_PER_MB_ESTIMATE > 0