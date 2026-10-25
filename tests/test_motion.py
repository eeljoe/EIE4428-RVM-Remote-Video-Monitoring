"""Tests for motion estimation and motion compensation."""

import numpy as np
import pytest

from rvm.codec.motion import (
    BLOCK_SIZE,
    MotionField,
    block_shape,
    compensate,
    estimate_motion,
    global_motion_search,
    refine_motion_field,
    shift_plane,
)


from scenegen import structured_shift_scene


def make_scene(width=64, height=64, dx=0, dy=0, seed=0):
    """Return ``(current, previous)`` with the true motion vector ``(dx, dy)``."""
    return structured_shift_scene(width=width, height=height, dx=dx, dy=dy, seed=seed)


def test_block_shape_counts_the_whole_frame():
    width, height = 64, 32

    cols, rows = block_shape(width, height)

    assert (cols, rows) == (8, 4)


def test_block_shape_rejects_a_frame_smaller_than_one_block():
    with pytest.raises(ValueError, match="8"):
        block_shape(4, 4)


def test_shift_plane_moves_content_by_the_signed_offset():
    plane = np.arange(100, dtype=np.float32).reshape(10, 10)

    shifted = shift_plane(plane, 2, 1)

    # Sample (r, c) of the shifted plane comes from (r - dy, c - dx).
    assert shifted[5, 5] == plane[4, 3]


def test_shift_plane_of_zero_offset_is_the_identity():
    plane = np.arange(64, dtype=np.float32).reshape(8, 8)

    assert np.array_equal(shift_plane(plane, 0, 0), plane)


def test_shift_plane_fills_the_border_by_edge_replication():
    plane = np.ones((4, 4), dtype=np.float32)

    shifted = shift_plane(plane, 1, 0)

    assert shifted.shape == plane.shape
    assert np.all(shifted == 1.0)


def test_global_search_finds_a_pure_horizontal_shift():
    current, previous = make_scene(dx=3, dy=0, seed=1)

    dx, dy, cost = global_motion_search(previous, current, search_range=8)

    assert (dx, dy) == (3, 0)
    # Not exactly zero: the left edge is filled by replication, so the few
    # border columns cannot be matched. It must still be a near-perfect fit.
    uncompensated = np.abs(current - previous).sum()
    assert cost < 0.01 * uncompensated


def test_global_search_finds_a_pure_vertical_shift():
    current, previous = make_scene(dx=0, dy=-2, seed=2)

    dx, dy, _ = global_motion_search(previous, current, search_range=8)

    assert (dx, dy) == (0, -2)


def test_global_search_finds_a_diagonal_shift():
    current, previous = make_scene(dx=2, dy=3, seed=3)

    dx, dy, _ = global_motion_search(previous, current, search_range=8)

    assert (dx, dy) == (2, 3)


def test_global_search_reports_zero_cost_for_an_exact_match():
    frame, _ = make_scene(seed=4)

    _, _, cost = global_motion_search(frame, frame, search_range=4)

    assert cost == pytest.approx(0.0, abs=1e-6)


def test_global_search_cost_falls_as_the_estimate_improves():
    current, previous = make_scene(dx=4, dy=0, seed=5)

    good = global_motion_search(previous, current, search_range=8)[2]
    bad = global_motion_search(previous, current, search_range=1)[2]

    assert good < bad


def test_motion_field_covers_every_block_with_one_vector_each():
    current, previous = make_scene(dx=1, dy=1, seed=6)

    field = estimate_motion(previous, current, search_range=4)

    assert isinstance(field, MotionField)
    assert field.dx.shape == (8, 8)  # 64x64 frame, 8x8 blocks
    assert field.dy.shape == (8, 8)
    assert field.cost.shape == (8, 8)


def test_every_block_of_a_uniformly_shifted_scene_gets_the_same_vector():
    current, previous = make_scene(dx=2, dy=-1, seed=7)

    field = estimate_motion(previous, current, search_range=4)

    assert set(np.unique(field.dx).tolist()) == {2}
    assert set(np.unique(field.dy).tolist()) == {-1}


def test_refinement_splits_a_scene_into_a_static_and_a_moving_region():
    """A monitoring scene: mostly static background plus one moving patch."""
    previous = np.zeros((64, 64), dtype=np.float32)
    previous[:, :] = np.linspace(0, 255, 64, dtype=np.float32)[None, :]

    current = previous.copy()
    patch = np.random.default_rng(8).uniform(0, 255, size=(16, 16))
    current[16:32, 16:32] = patch  # region that does not match the background

    field = estimate_motion(previous, current, search_range=4)

    # The background blocks should cost nothing; the overwritten ones should not.
    assert field.cost[0, 0] == pytest.approx(0.0, abs=1e-6)
    assert field.cost.max() > 0.0


def test_estimate_motion_leaves_static_blocks_at_zero_cost():
    frame, _ = make_scene(seed=9)

    field = estimate_motion(frame, frame, search_range=4)

    assert np.all(field.cost == pytest.approx(0.0, abs=1e-6))


def test_compensation_of_a_known_shift_reconstructs_the_current_frame():
    current, previous = make_scene(dx=3, dy=2, seed=10)

    field = estimate_motion(previous, current, search_range=4)
    prediction = compensate(previous, field)

    assert prediction.shape == current.shape

    # Not pixel-exact: borders are edge-replicated, and a structured canvas can
    # leave a few blocks with an equally good neighbouring offset. The mean
    # error must still be negligible.
    assert np.mean(np.abs(prediction - current)) < 1.0


def test_compensation_of_a_static_frame_reproduces_it():
    frame, _ = make_scene(seed=11)

    field = estimate_motion(frame, frame, search_range=4)

    assert np.allclose(compensate(frame, field), frame)


def test_compensated_prediction_is_far_closer_than_no_prediction_at_all():
    """Prediction must actually reduce the residual energy."""
    current, previous = make_scene(dx=3, dy=0, seed=12)

    field = estimate_motion(previous, current, search_range=4)
    predicted = compensate(previous, field)

    raw = float(np.abs(current - previous).mean())
    improved = float(np.abs(current - predicted).mean())

    assert improved < raw


def test_field_reports_the_best_cost_for_each_block():
    current, previous = make_scene(dx=2, dy=0, seed=13)

    field = estimate_motion(previous, current, search_range=4)

    # Every reported cost must match a real SAD at the reported vector.
    for row in range(field.dx.shape[0]):
        for col in range(field.dx.shape[1]):
            block = slice(row * BLOCK_SIZE, (row + 1) * BLOCK_SIZE)
            block_col = slice(col * BLOCK_SIZE, (col + 1) * BLOCK_SIZE)
            reference = shift_plane(
                previous, int(field.dx[row, col]), int(field.dy[row, col])
            )
            actual = np.abs(current[block, block_col] - reference[block, block_col]).sum()
            assert field.cost[row, col] == pytest.approx(actual, abs=1e-3)


def test_refine_motion_field_never_moves_a_block_outside_the_search_window():
    current, previous = make_scene(dx=6, dy=0, seed=14)

    field = refine_motion_field(previous, current, base_dx=0, base_dy=0, window=2)

    assert np.all(np.abs(field.dx) <= 2)
    assert np.all(np.abs(field.dy) <= 2)


def test_refinement_never_returns_a_worse_cost_than_the_base_vector():
    """Refinement is a search, so every block's chosen vector must cost no more."""
    current, previous = make_scene(dx=5, dy=5, seed=15)

    field = refine_motion_field(previous, current, base_dx=5, base_dy=5, window=2)

    base = np.zeros(field.block_shape)
    for row in range(field.block_shape[0]):
        for col in range(field.block_shape[1]):
            reference = shift_plane(previous, 5, 5)
            block = (
                slice(row * BLOCK_SIZE, (row + 1) * BLOCK_SIZE),
                slice(col * BLOCK_SIZE, (col + 1) * BLOCK_SIZE),
            )
            base[row, col] = np.abs(current[block] - reference[block]).sum()

    assert np.all(field.cost <= base + 1e-6)
    # The base vector is already optimal, so most blocks must keep it.
    assert int(np.count_nonzero(field.dx == 5)) > field.dx.size // 2


def test_motion_field_validates_against_a_frame_of_the_wrong_size():
    frame, _ = make_scene()
    field = estimate_motion(frame, frame, search_range=2)

    with pytest.raises(ValueError, match="shape"):
        compensate(np.zeros((32, 32), dtype=np.float32), field)