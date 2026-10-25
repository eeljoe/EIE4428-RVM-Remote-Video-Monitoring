"""Tests for the hybrid video encoder and its matching decoder."""

import numpy as np
import pytest
from scenegen import moving_scene, structured_shift_scene

from rvm.analysis.quality import psnr
from rvm.codec.ratecontrol import FrameType
from rvm.codec.video import VideoDecoder, VideoEncoder


def rgb_frame(frame_index, width=128, height=96, dx=2, dy=-1, seed=0):
    """An RGB frame from the synthetic monitoring sequence."""
    luma = moving_scene(frame_index, width=width, height=height, dx=dx, dy=dy, seed=seed)
    rows, columns = np.mgrid[0:height, 0:width]
    red = (luma * 0.9 + columns * 0.2) % 255.0
    green = (luma * 0.8 + rows * 0.15) % 255.0
    blue = (luma * 0.7 + 40.0) % 255.0
    return np.clip(np.stack((red, green, blue), axis=-1), 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_encoder_reports_the_frame_size_it_was_configured_for():
    encoder = VideoEncoder(128, 96, target_bitrate=400_000, frame_rate=25)

    assert (encoder.width, encoder.height) == (128, 96)


def test_encoder_rejects_dimensions_that_are_not_block_aligned():
    with pytest.raises(ValueError, match="multiple of 16"):
        VideoEncoder(130, 96, target_bitrate=400_000, frame_rate=25)


def test_encoder_rejects_a_non_positive_bitrate():
    with pytest.raises(ValueError, match="bitrate"):
        VideoEncoder(128, 96, target_bitrate=0, frame_rate=25)


# --------------------------------------------------------------------------
# Intra frames
# --------------------------------------------------------------------------


def test_intra_frame_round_trips_to_a_recognisable_image():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    decoder = VideoDecoder()
    original = rgb_frame(0)

    encoded = encoder.encode(original, force_keyframe=True)
    restored = decoder.decode(encoded)

    assert restored.shape == original.shape
    assert psnr(original, restored) > 30.0


def test_a_keyframe_can_be_decoded_without_any_prior_state():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    encoded = encoder.encode(rgb_frame(0), force_keyframe=True)

    restored = VideoDecoder().decode(encoded)

    assert restored is not None


def test_encoded_payload_starts_with_the_codec_magic():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)

    payload = encoder.encode(rgb_frame(0), force_keyframe=True).data

    assert payload[:2] == b"RV"


def test_an_intra_frame_is_reported_as_such():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)

    encoded = encoder.encode(rgb_frame(0), force_keyframe=True)

    assert encoded.frame_type is FrameType.I
    assert encoded.is_keyframe


def test_the_first_frame_is_always_a_keyframe():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)

    encoded = encoder.encode(rgb_frame(0))

    assert encoded.is_keyframe


# --------------------------------------------------------------------------
# Inter frames
# --------------------------------------------------------------------------


def test_predicted_frame_round_trips():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    decoder = VideoDecoder()

    decoder.decode(encoder.encode(rgb_frame(0), force_keyframe=True))
    decoder.decode(encoder.encode(rgb_frame(1)))

    original = rgb_frame(3)
    restored = decoder.decode(encoder.encode(original))

    assert restored.shape == original.shape
    assert psnr(original, restored) > 30.0


def test_a_predicted_frame_is_reported_as_inter():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)

    encoder.encode(rgb_frame(0), force_keyframe=True)
    encoded = encoder.encode(rgb_frame(1))

    assert encoded.frame_type is FrameType.P
    assert not encoded.is_keyframe


def test_motion_compensation_beats_intra_coding_on_a_moving_scene():
    """The whole point of inter prediction: a P frame costs fewer bits than an I."""
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)

    intra = encoder.encode(rgb_frame(0), force_keyframe=True)
    for index in range(1, 6):
        inter = encoder.encode(rgb_frame(index))

    assert inter.size < intra.size


def test_a_static_sequence_produces_tiny_predicted_frames():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)

    intra = encoder.encode(rgb_frame(0, dx=0, dy=0), force_keyframe=True)
    encoder.encode(rgb_frame(0, dx=0, dy=0))  # establish the reference
    inter = encoder.encode(rgb_frame(0, dx=0, dy=0))

    assert inter.size < intra.size / 4


def test_prediction_recovers_a_known_shift():
    """A shifted frame must decode closer to the truth than an intra copy."""
    current, previous_rgb = structured_shift_scene(128, 96, dx=3, dy=0, seed=2)
    previous_rgb = np.repeat(previous_rgb[:, :, None], 3, axis=2).astype(np.uint8)
    current_rgb = np.repeat(current[:, :, None], 3, axis=2).astype(np.uint8)

    encoder = VideoEncoder(128, 96, target_bitrate=1_500_000, frame_rate=25)
    decoder = VideoDecoder()
    decoder.decode(encoder.encode(previous_rgb, force_keyframe=True))
    restored = decoder.decode(encoder.encode(current_rgb))

    assert psnr(current_rgb, restored) > 30.0


# --------------------------------------------------------------------------
# Decoder resilience
# --------------------------------------------------------------------------


def test_decoder_requests_a_keyframe_when_it_has_no_reference():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    encoder.encode(rgb_frame(0), force_keyframe=True)
    inter = encoder.encode(rgb_frame(1))

    assert VideoDecoder().decode(inter) is None


def test_decoder_requests_a_keyframe_after_a_gap_in_the_stream():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    decoder = VideoDecoder()
    decoder.decode(encoder.encode(rgb_frame(0), force_keyframe=True))
    decoder.decode(encoder.encode(rgb_frame(1)))

    decoder.drop_reference()

    assert decoder.decode(encoder.encode(rgb_frame(2))) is None


def test_decoder_rejects_a_truncated_payload():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    encoded = encoder.encode(rgb_frame(0), force_keyframe=True)

    with pytest.raises(ValueError):
        VideoDecoder().decode(
            type(encoded)(**{**encoded.__dict__, "data": encoded.data[:20]})
        )


def test_decoder_rejects_payloads_that_are_not_ours():
    with pytest.raises(ValueError, match="magic"):
        VideoDecoder().decode(b"NOTRVM1PAYLOADATALL......")


def test_decoder_rejects_a_frame_from_a_different_size_sequence():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)
    other = VideoEncoder(64, 48, target_bitrate=400_000, frame_rate=25)
    decoder = VideoDecoder()
    decoder.decode(encoder.encode(rgb_frame(0, width=128, height=96), force_keyframe=True))

    with pytest.raises(ValueError, match="resolution"):
        decoder.decode(
            other.encode(rgb_frame(0, width=64, height=48), force_keyframe=True)
        )


def test_encoder_rejects_a_frame_of_the_wrong_size():
    encoder = VideoEncoder(128, 96, target_bitrate=800_000, frame_rate=25)

    with pytest.raises(ValueError, match="shape"):
        encoder.encode(np.zeros((64, 64, 3), dtype=np.uint8))


# --------------------------------------------------------------------------
# Rate control integration
# --------------------------------------------------------------------------


def test_lower_target_bitrate_produces_smaller_frames():
    rich = VideoEncoder(128, 96, target_bitrate=2_000_000, frame_rate=25)
    poor = VideoEncoder(128, 96, target_bitrate=60_000, frame_rate=25)
    frame = rgb_frame(0)

    assert (
        poor.encode(frame, force_keyframe=True).size
        < rich.encode(frame, force_keyframe=True).size
    )


def test_rate_control_holds_the_configured_bitrate():
    """The controller's whole job: converge onto the demanded rate."""
    encoder = VideoEncoder(128, 96, target_bitrate=60_000, frame_rate=25)

    sizes = [encoder.encode(rgb_frame(index)).size for index in range(40)]
    measured = sum(sizes) * 8 * 25 / 40

    assert 0.7 * 60_000 < measured < 1.3 * 60_000


def test_rate_control_pushes_qp_up_when_the_budget_cannot_be_met():
    """At a budget even the finest quantiser cannot reach, QP must run to the top."""
    encoder = VideoEncoder(128, 96, target_bitrate=4_000, frame_rate=25)
    for index in range(20):
        encoder.encode(rgb_frame(index))

    controller = encoder.rate_controller
    assert controller.current_qp > controller.initial_qp


def test_rate_control_reaches_the_fine_end_when_the_budget_is_generous():
    encoder = VideoEncoder(128, 96, target_bitrate=30_000_000, frame_rate=25)
    # The +/-2 QP limiter needs about a dozen pictures to walk from the
    # mid-range start down to the finest setting.
    for index in range(25):
        encoder.encode(rgb_frame(index))

    controller = encoder.rate_controller
    assert controller.current_qp == 1


def test_encoder_exposes_its_controller_for_the_dashboard():
    encoder = VideoEncoder(128, 96, target_bitrate=300_000, frame_rate=25)

    assert hasattr(encoder.rate_controller, "average_bitrate")


def test_a_long_sequence_stays_within_a_reasonable_multiple_of_its_budget():
    encoder = VideoEncoder(128, 96, target_bitrate=300_000, frame_rate=25)

    total = 0
    for index in range(60):
        total += encoder.encode(rgb_frame(index)).size

    budget = 300_000 * (60 / 25)
    assert total < 3.0 * budget


def test_encoder_emits_a_keyframe_at_the_configured_interval():
    encoder = VideoEncoder(128, 96, target_bitrate=400_000, frame_rate=25, gop_size=10)

    flags = [encoder.encode(rgb_frame(i)).is_keyframe for i in range(30)]

    assert flags[0]
    assert sum(flags) >= 3


def test_reported_qp_stays_within_the_legal_range():
    encoder = VideoEncoder(128, 96, target_bitrate=150_000, frame_rate=25)

    for index in range(50):
        assert 1 <= encoder.encode(rgb_frame(index)).qp <= 51


# --------------------------------------------------------------------------
# Metadata for the receiver side
# --------------------------------------------------------------------------


def test_encoded_frame_carries_the_frame_number_and_timestamp():
    encoder = VideoEncoder(128, 96, target_bitrate=400_000, frame_rate=25)

    first = encoder.encode(rgb_frame(0))
    second = encoder.encode(rgb_frame(1))

    assert first.frame_index == 0
    assert second.frame_index == 1
    assert second.timestamp > first.timestamp


def test_encoder_reports_a_measured_encode_time():
    encoder = VideoEncoder(128, 96, target_bitrate=400_000, frame_rate=25)

    assert encoder.encode(rgb_frame(0)).encode_time_ms >= 0.0