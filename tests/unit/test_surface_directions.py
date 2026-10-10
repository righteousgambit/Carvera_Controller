"""Independent exact-direction bounds and full-face continuous culling oracles."""

import math
import random
from fractions import Fraction as F

import pytest

from carveracontroller.machine.surface_directions import (
    DIRECTIONS,
    overlap_interval,
    point_bounds,
    project,
    union_bounds,
)
from tests.unit.test_surface_motion_exact import full_axis_reference


def qrows(rows):
    return tuple(tuple(F(x) for x in p) for triangle in rows for p in triangle)


@pytest.mark.parametrize("scale", [math.ulp(0.0), 1.0, 100000.0])
def test_complete_direction_bounds_and_union_keep_exact_subnormal_input(scale):
    rows = tuple(tuple(F(v * scale) for v in p) for p in ((0, 0, 0), (1, 2, 3), (-1, -3, -2)))
    expected = tuple(
        (min(sum(a * b for a, b in zip(axis, p)) for p in rows), max(sum(a * b for a, b in zip(axis, p)) for p in rows))
        for axis in DIRECTIONS
    )
    assert point_bounds(rows) == expected
    assert union_bounds(tuple(point_bounds((p,)) for p in rows)) == expected


@pytest.mark.parametrize("error", [0.0, 1e-6, 0.25])
def test_empty_direction_interval_proves_every_original_pair_separated(error):
    rng = random.Random(5301)
    empty = 0
    for _ in range(100):
        first = tuple(tuple(tuple(rng.uniform(-2, 2) for _ in range(3)) for _ in range(3)) for _ in range(3))
        second = tuple(tuple(tuple(rng.uniform(-2, 2) for _ in range(3)) for _ in range(3)) for _ in range(2))
        shift, delta = (tuple(F(rng.uniform(-8, 8)) for _ in range(3)) for _ in range(2))
        bounds = overlap_interval(
            point_bounds(qrows(first)),
            point_bounds(qrows(second)),
            project(shift),
            project(delta),
            F(error),
            (F(0), F(1)),
        )
        for a in first:
            for b in second:
                interval = full_axis_reference(a, b, shift, delta, error)
                if interval is not None:
                    assert bounds is not None and bounds[0] <= interval[0] <= interval[1] <= bounds[1]
        empty += bounds is None
    assert empty > 20


@pytest.mark.parametrize("direction", [(1, 1, 0), (1, 0, 1), (0, 1, 1)])
def test_closed_exact_contact_endpoints_padding_and_nonoverlapping_times(direction):
    zero = point_bounds(((F(0), F(0), F(0)),))
    vector = tuple(F(v) for v in direction)
    other = point_bounds((vector,))
    assert overlap_interval(zero, other, project((F(0),) * 3), project(vector), F(0), (F(0), F(1))) == (F(1), F(1))
    assert overlap_interval(zero, other, project(vector), project((F(0),) * 3), F(0), (F(0), F(1))) == (F(0), F(1))
    assert overlap_interval(zero, other, project((F(0),) * 3), project(vector), F(0), (F(0), F(1, 2))) is None
    assert overlap_interval(zero, other, project((F(0),) * 3), project((F(0),) * 3), F(1), (F(0), F(1))) is not None


def test_oblique_bounds_reject_empty_axis_box_space_without_rounding():
    a = ((F(0), F(0), F(0)), (F(2), F(0), F(0)), (F(0), F(2), F(0)))
    b = ((F(2), F(2), F(0)), (F(2), F(1, 2), F(0)), (F(1, 2), F(2), F(0)))
    # Coordinate boxes overlap, but the x+y node projections prove separation.
    assert all(
        min(p[i] for p in a) <= max(p[i] for p in b) and min(p[i] for p in b) <= max(p[i] for p in a) for i in range(3)
    )
    zeros = project((F(0),) * 3)
    assert overlap_interval(point_bounds(a), point_bounds(b), zeros, zeros, F(0), (F(0), F(1))) is None
    assert overlap_interval(point_bounds(a), point_bounds(b), zeros, zeros, F(1, 4), (F(0), F(1))) == (F(0), F(1))


@pytest.mark.parametrize("error", [0.0, 1e-6, 0.25])
def test_direct_coordinate_box_slabs_match_original_general_exact_projection(error):
    from carveracontroller.machine.surface_directions import box_interval
    from carveracontroller.machine.surface_motion import qpoint, slab_interval

    rng = random.Random(9382)
    axes = tuple(qpoint(p) for p in ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    for _ in range(200):
        boxes = []
        for _ in range(2):
            a, b = (tuple(rng.uniform(-8, 8) for _ in range(3)) for _ in range(2))
            boxes.append((tuple(min(a[i], b[i]) for i in range(3)), tuple(max(a[i], b[i]) for i in range(3))))
        shift, delta = (qpoint(tuple(rng.uniform(-12, 12) for _ in range(3))) for _ in range(2))
        expected = slab_interval(
            tuple(qpoint(p) for p in boxes[0]), tuple(qpoint(p) for p in boxes[1]), shift, delta, axes, F(error)
        )
        assert box_interval(*boxes, shift, delta, F(error)) == expected
