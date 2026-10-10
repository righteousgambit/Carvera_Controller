"""Original full-axis rational oracle versus exact static integer embedding."""

import math
import random
from fractions import Fraction as F

import pytest

from carveracontroller.machine.surface_motion import qpoint
from carveracontroller.machine.surface_static import static_contact
from tests.unit.test_surface_motion_exact import full_axis_reference


@pytest.mark.parametrize("error", [0.0, 1e-6, 0.25])
def test_static_integer_predicate_matches_full_original_rational_axes(error):
    rng = random.Random(1329)
    for _ in range(160):
        first, second = (tuple(tuple(rng.uniform(-8, 8) for _ in range(3)) for _ in range(3)) for _ in range(2))
        shift = tuple(rng.uniform(-12, 12) for _ in range(3))
        expected = full_axis_reference(first, second, shift, (0, 0, 0), error)
        assert static_contact(
            tuple(qpoint(p) for p in first), tuple(qpoint(p) for p in second), qpoint(shift), F(error)
        ) == (expected is not None)


@pytest.mark.parametrize("scale", [math.ulp(0.0), 1.0, 100000.0])
@pytest.mark.parametrize("axis", [0, 1, 2])
def test_exact_coplanar_endpoint_degeneracy_permutations_and_subnormals(scale, axis):
    def point(x, y, z):
        row = x * scale, y * scale, z * scale
        return row[axis:] + row[:axis]

    first = (point(0, 0, 0), point(2, 0, 0), point(0, 2, 0))
    rows = (first[::-1], (point(1, 1, 0),) * 3, (point(0, 0, 0), point(1, 1, 0), point(1, 1, 0)))
    for second in rows:
        for shift, error in ((point(2, 0, 0), 0.0), (point(0, 0, 1), 0.0), (point(0, 0, 1), min(scale, 2000.0))):
            expected = full_axis_reference(first, second, shift, (0, 0, 0), error)
            assert static_contact(
                tuple(qpoint(p) for p in first), tuple(qpoint(p) for p in second), qpoint(shift), F(error)
            ) == (expected is not None)


@pytest.mark.parametrize("second_coordinate", [F(1, 2), F(1, 3)])
def test_nondyadic_input_cannot_be_silently_rounded_to_grid(second_coordinate):
    first = ((F(1, 3), F(0), F(0)),) * 3
    second = ((second_coordinate, F(0), F(0)),) * 3
    with pytest.raises(ValueError, match="dyadic"):
        static_contact(first, second, (F(0),) * 3, F(0))
