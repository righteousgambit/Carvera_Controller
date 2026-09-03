"""Tests for visual regression comparison tolerance.

Exact pixel comparison fails on a GPU driver update or a font hinting
change, and a check that cries wolf gets disabled. These assert the
comparison distinguishes rendering noise from an actual UI change.
"""

import pytest
from PIL import Image

from tests.integration.conftest import (
    MAX_DIFFERING_FRACTION,
    PIXEL_CHANNEL_TOLERANCE,
    screenshot_difference,
)

_SIZE = (200, 100)


def _image(colour=(30, 30, 30)):
    return Image.new("RGB", _SIZE, colour)


def test_identical_images_differ_by_nothing():
    assert screenshot_difference(_image(), _image()) == 0.0


def test_noise_within_tolerance_is_ignored():
    """Every pixel shifted slightly, as a driver revision would."""
    shifted = _image((30 + PIXEL_CHANNEL_TOLERANCE, 30, 30))

    assert screenshot_difference(_image(), shifted) == 0.0


def test_noise_beyond_tolerance_counts():
    shifted = _image((30 + PIXEL_CHANNEL_TOLERANCE + 20, 30, 30))

    assert screenshot_difference(_image(), shifted) == pytest.approx(1.0)


def test_a_small_changed_region_stays_under_the_limit():
    """A handful of pixels moving is not a regression."""
    changed = _image()
    for x in range(4):
        for y in range(4):
            changed.putpixel((x, y), (255, 255, 255))

    fraction = screenshot_difference(_image(), changed)

    assert 0 < fraction <= MAX_DIFFERING_FRACTION


def test_a_meaningful_change_exceeds_the_limit():
    """A widget appearing or moving touches far more than the threshold."""
    changed = _image()
    for x in range(60):
        for y in range(40):
            changed.putpixel((x, y), (255, 255, 255))

    assert screenshot_difference(_image(), changed) > MAX_DIFFERING_FRACTION


def test_an_empty_image_does_not_divide_by_zero():
    empty = Image.new("RGB", (0, 0))
    assert screenshot_difference(empty, empty) == 0.0
