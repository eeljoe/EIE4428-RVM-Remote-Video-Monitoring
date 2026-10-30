"""Multi-object tracking: turning a motion mask into identities over time.

The motion detector answers "did anything move"; a monitoring operator's next
question is "*what* moved, and where did it go".  Splitting the changed-pixel
mask into connected regions gives one box per moving object, and associating
those boxes across frames keeps each object's identity and trail.
"""

import numpy as np
import pytest

from rvm.analysis.track import CentroidTracker, regions_from_mask

WIDTH, HEIGHT = 160, 112


def mask_with(*rects):
    """A binary mask with filled ``(top, left, height, width)`` rectangles."""
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    for top, left, height, width in rects:
        mask[top : top + height, left : left + width] = 1
    return mask


# --------------------------------------------------------------------------
# Mask -> regions
# --------------------------------------------------------------------------


def test_an_empty_mask_has_no_regions():
    assert regions_from_mask(np.zeros((HEIGHT, WIDTH), dtype=np.uint8)) == []


def test_one_blob_gives_one_box_covering_it():
    regions = regions_from_mask(mask_with((10, 20, 12, 30)))

    assert regions == [(10, 20, 22, 50)]


def test_two_separated_blobs_are_two_regions():
    regions = regions_from_mask(mask_with((10, 10, 8, 8), (60, 100, 10, 14)))

    assert regions == [(10, 10, 18, 18), (60, 100, 70, 114)]


def test_diagonally_touching_pixels_are_one_region():
    """Eight-connectivity: a moving edge leaves diagonal speckle trails."""
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    mask[10, 10] = 1
    mask[11, 11] = 1
    mask[12, 12] = 1

    regions = regions_from_mask(mask, min_area=1)

    assert len(regions) == 1


def test_regions_smaller_than_the_minimum_are_dropped():
    """Erosion leaves speckles; a tracked object must be bigger than noise."""
    regions = regions_from_mask(
        mask_with((10, 10, 2, 2), (60, 60, 12, 12)), min_area=16
    )

    assert regions == [(60, 60, 72, 72)]


def test_regions_come_back_in_scan_order():
    regions = regions_from_mask(mask_with((60, 60, 10, 10), (10, 10, 10, 10)))

    assert regions[0] == (10, 10, 20, 20)
    assert regions[1] == (60, 60, 70, 70)


# --------------------------------------------------------------------------
# Regions -> tracks
# --------------------------------------------------------------------------


def box_at(top, left, size=10):
    """A square ``(top, left, bottom, right)`` detection box."""
    return (top, left, top + size, left + size)


def test_a_moving_object_keeps_its_identity():
    tracker = CentroidTracker()

    first = tracker.update([box_at(10, 10)])
    second = tracker.update([box_at(12, 14)])
    third = tracker.update([box_at(14, 18)])

    assert first[0].id == second[0].id == third[0].id


def test_a_track_remembers_where_it_has_been():
    tracker = CentroidTracker()

    tracker.update([box_at(10, 10)])
    tracker.update([box_at(10, 20)])
    (track,) = tracker.update([box_at(10, 30)])

    xs = [point[0] for point in track.snapshot()["trail"]]
    assert xs[0] < xs[1] < xs[2]


def test_a_new_object_gets_a_new_identity():
    tracker = CentroidTracker()

    tracker.update([box_at(10, 10)])
    tracks = tracker.update([box_at(10, 10), box_at(70, 110)])

    assert {track.id for track in tracks} == {1, 2}


def test_a_detection_too_far_away_starts_a_new_track():
    """A jump across the frame is a different object, not a fast one."""
    tracker = CentroidTracker(max_distance=30)

    tracker.update([box_at(10, 10)])
    (track,) = tracker.update([box_at(80, 120)])

    assert track.id == 2


def test_a_vanished_object_survives_a_short_occlusion():
    tracker = CentroidTracker(max_missed=3)

    tracker.update([box_at(10, 10)])
    tracker.update([box_at(12, 14)])
    assert tracker.update([]) == []
    (track,) = tracker.update([box_at(14, 18)])

    assert track.id == 1


def test_a_vanished_object_eventually_expires():
    tracker = CentroidTracker(max_missed=2)

    tracker.update([box_at(10, 10)])
    for _ in range(3):
        tracker.update([])
    (track,) = tracker.update([box_at(10, 10)])

    assert track.id == 2


def test_the_trail_is_bounded():
    tracker = CentroidTracker(trail_length=5)

    for step in range(9):
        (track,) = tracker.update([box_at(10, 10 + step)])

    assert len(track.trail) == 5


def test_reset_clears_tracks_and_identities():
    tracker = CentroidTracker()

    tracker.update([box_at(10, 10)])
    tracker.reset()
    (track,) = tracker.update([box_at(10, 10)])

    assert track.id == 1


def test_a_track_reports_its_box_and_centre():
    (track,) = CentroidTracker().update([box_at(10, 20, size=10)])

    assert track.bbox == (10, 20, 20, 30)
    snapshot = track.snapshot()
    assert snapshot["id"] == 1
    assert snapshot["bbox"] == [10, 20, 20, 30]
    # Snapshot coordinates are (x, y): column first, row second.
    assert snapshot["centroid"] == [25, 15]
    assert snapshot["trail"] == [[25, 15]]


def test_two_objects_tracked_independently():
    tracker = CentroidTracker()

    tracker.update([box_at(10, 10), box_at(60, 100)])
    tracks = tracker.update([box_at(12, 14), box_at(62, 96)])

    by_id = {track.id: track for track in tracks}
    assert by_id[1].bbox == (12, 14, 22, 24)
    assert by_id[2].bbox == (62, 96, 72, 106)
