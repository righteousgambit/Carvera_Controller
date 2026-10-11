"""Independent analytic continuous rotation cases and rational witness checks."""

from fractions import Fraction as F
from itertools import permutations

import pytest

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.machine.rotating_surface import box_candidate, triangle_contact
from carveracontroller.machine.surface_motion import qpoint

SECTION = AxialEnvelope("cutter", 0, 2, 1)


@pytest.mark.parametrize(
    "triangle,expected",
    [
        (((2, 2, 1), (3, 2, 1), (2, 3, 1)), False),
        (((1, 0, 1), (2, 1, 1), (2, -1, 1)), True),
        (((-2, -2, 1), (2, -2, 1), (0, 2, 1)), True),
        (((-2, -2, 3), (2, -2, 3), (0, 2, 3)), False),
        (((-2, -2, 2), (2, -2, 2), (0, 2, 2)), True),
        (((1, 0, 1), (1, 0, 1), (1, 0, 1)), True),
        (((1.0001, 0, 1), (1.0001, 0, 1), (1.0001, 0, 1)), False),
        (((-2, 0, 1), (2, 0, 1), (2, 0, 1)), True),
    ],
)
def test_static_disk_triangle_caps_corners_degenerate_and_closed_tangencies(triangle, expected):
    for order in permutations(triangle):
        hit = triangle_contact(SECTION, order)
        assert (hit is not None) == expected
        if hit:
            assert sum(hit.barycentric) == 1 and min(hit.barycentric) >= 0 and 0 <= hit.sample <= 1
            assert hit.point == tuple(
                sum((hit.barycentric[i] * F(order[i][j]) for i in range(3)), F(0)) for j in range(3)
            )
            assert 0 <= hit.point[2] <= 2
            assert hit.radial_distance_squared == hit.point[0] ** 2 + hit.point[1] ** 2 <= 1


def test_interior_collision_between_disjoint_endpoints_and_exact_witness():
    triangle = ((0, 0, 1), (0, 0, 1), (0, 0, 1))
    assert triangle_contact(SECTION, triangle, (-3, 0, 0)) is None
    assert triangle_contact(SECTION, triangle, (3, 0, 0)) is None
    hit = triangle_contact(SECTION, triangle, (-3, 0, 0), (6, 0, 0))
    assert hit and hit.sample == F(1, 2) and hit.radial_distance_squared == 0


@pytest.mark.parametrize(
    "shift,delta,expected",
    [
        ((-3, 0, -2), (6, 0, 4), True),
        ((-3, 0, -2), (6, 0, 12), False),
        ((0, 0, -3), (0, 0, 4), True),
        ((0, 0, -3), (0, 0, 1), True),
        ((0, 0, -3), (0, 0, F(1, 2)), False),
    ],
)
def test_axial_and_radial_contact_must_share_the_same_time(shift, delta, expected):
    triangle = ((0, 0, 0),) * 3
    delta = tuple(float(v) for v in delta)
    hit = triangle_contact(SECTION, triangle, shift, delta)
    assert (hit is not None) == expected
    if hit:
        center = tuple(F(shift[j]) + hit.sample * F(delta[j]) for j in range(3))
        assert 0 <= -center[2] <= 2
        assert center[0] ** 2 + center[1] ** 2 <= 1


def test_extremely_small_motion_and_outward_position_allowance():
    small = 2**-1074
    section = AxialEnvelope("shank", 0, small, small)
    hit = triangle_contact(section, ((small, 0, 0),) * 3)
    assert hit and hit.radial_distance_squared == F(small) ** 2
    triangle = ((1.1, 0, 2.1),) * 3
    assert triangle_contact(SECTION, triangle) is None
    assert triangle_contact(SECTION, triangle, position_error_mm=0.2)


def test_exact_node_box_culling_keeps_every_analytic_contact():
    for x in range(-3, 4):
        for y in range(-3, 4):
            for z in range(-2, 4):
                tri = ((x, y, z), (x + 0.5, y, z), (x, y + 0.5, z + 0.5))
                box = ((x, y, z), (x + 0.5, y + 0.5, z + 0.5))
                shift = (-4, 0, -1)
                delta = (8, 0, 2)
                hit = triangle_contact(SECTION, tri, shift, delta)
                if hit:
                    assert box_candidate(SECTION, box, qpoint(shift), qpoint(delta), 0)
    assert not box_candidate(SECTION, ((1, 1, 0), (2, 2, 2)), qpoint((0, 0, 0)), qpoint((0, 0, 0)), 0)


def test_cancellation_and_untrusted_dimensions_are_not_separation():
    with pytest.raises(InterruptedError, match="cancelled"):
        triangle_contact(SECTION, ((0, 0, 1),) * 3, cancelled=lambda: True)
    for error in (True, -1, float("nan"), 2001):
        with pytest.raises(ValueError, match="allowance"):
            triangle_contact(SECTION, ((0, 0, 1),) * 3, position_error_mm=error)
    with pytest.raises(ValueError, match="bounded"):
        triangle_contact(AxialEnvelope("holder", 0, 10001, 1), ((0, 0, 1),) * 3)
