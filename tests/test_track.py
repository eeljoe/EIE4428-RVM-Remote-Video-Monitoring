"""Multi-object tracking: turning a motion mask into identities over time.

The motion detector answers "did anything move"; a monitoring operator's next
question is "*what* moved, and where did it go".  Splitting the changed-pixel
mask into connected regions gives one box per moving object, and associating
those boxes across frames keeps each object's identity and trail.
"""

import numpy as np
import pytest

from rvm.analysis.track import regions_from_mask

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
