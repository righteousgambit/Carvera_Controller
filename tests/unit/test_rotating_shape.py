"""Independent exact shaped-tip, continuous-time and feasible-face controls."""

from fractions import Fraction as F
from itertools import permutations

import pytest

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope, ToolGeometry
from carveracontroller.machine.rotating_shape import RotatingShape, cutting_sections
from carveracontroller.machine.rotating_surface import triangle_contact

BALL = RotatingShape("cutter", 0, 2, 2, primitive="sphere", center_mm=2)
CONE = RotatingShape("cutter", 0, 2, 2, primitive="cone")


def point(x, y, z):
    return ((x, y, z),) * 3


@pytest.mark.parametrize("shape", [BALL, CONE])
@pytest.mark.parametrize(
    "z,x,expected",
    [(0, 1, False), (0, 0, True), (1, 1, True), (2, 2, True), (2, 2.1, False), (-0.1, 0, False), (2.1, 0, False)],
)
def test_exact_caps_and_tip_corners_do_not_use_full_cylinder(shape, z, x, expected):
    assert (triangle_contact(shape, point(x, 0, z)) is not None) == expected
    if z == 0 and x == 1:
        assert triangle_contact(AxialEnvelope("cutter", 0, 2, 2), point(x, 0, z)) is not None


@pytest.mark.parametrize("shape", [BALL, CONE])
def test_clear_endpoints_have_an_exact_interior_time_witness(shape):
    tri = point(0, 0, 1)
    assert triangle_contact(shape, tri, (-4, 0, 0)) is None
    assert triangle_contact(shape, tri, (4, 0, 0)) is None
    hit = triangle_contact(shape, tri, (-4, 0, 0), (8, 0, 0))
    assert hit and hit.sample == F(1, 2) and hit.point == (0, 0, 1)
    assert hit.barycentric[0] + hit.barycentric[1] + hit.barycentric[2] == 1


@pytest.mark.parametrize("shape", [BALL, CONE])
def test_complete_triangle_interior_and_all_permutations(shape):
    tri = ((-5, -4, 1), (5, -4, 1), (0, 5, 1))
    for ordered in permutations(tri):
        hit = triangle_contact(shape, ordered)
        assert hit and hit.point == (0, 0, 1) and min(hit.barycentric) > 0


def test_sphere_tangent_edge_and_diagonal_shared_time():
    # Neither end of this edge belongs to the ball. Its middle is tangent.
    hit = triangle_contact(BALL, ((-3, 2, 2), (3, 2, 2), (3, 2, 2)))
    assert hit and hit.point == (0, 2, 2) and hit.radial_distance_squared == 4
    # Independently minimize the point's squared distance to ball-center chord.
    for delta in ((8, 0, 0), (8, 0, 12), (8, 4, 8)):
        start = (-4, 0, -2)
        tri = point(0, 0, 1)
        valid = []
        for i in range(1001):
            t = F(i, 1000)
            h = 1 - start[2] - t * delta[2]
            if 0 <= h <= 2:
                valid.append(((-start[0] - t * delta[0]) ** 2 + (-start[1] - t * delta[1]) ** 2 + (h - 2) ** 2) <= 4)
        # Sampling supplies positive witnesses only; negative result checked by
        # analytical special cases, never claimed from a grid alone.
        result = triangle_contact(BALL, tri, start, delta)
        if any(valid):
            assert result is not None
        if delta == (8, 0, 0):
            assert result is None  # Point height is 3 for the entire chord.


def test_cone_false_endpoint_radius_and_exact_interior_stationary_face():
    tri = point(1, 0, 0.25)
    assert triangle_contact(CONE, tri) is None
    assert triangle_contact(CONE, tri, (0, 0, -1)) is not None
    # A thin edge lies inside the broad cylinder but outside the true cone.
    assert triangle_contact(CONE, ((1, 0, 0.25), (1, 1, 0.25), (1, 1, 0.5))) is None
    # The oblique triangle intersects the cone only along an edge interior.
    hit = triangle_contact(CONE, ((-3, 0, 1), (3, 0, 1), (3, 0, 1)))
    assert hit and hit.point == (0, 0, 1)


@pytest.mark.parametrize("shape", [BALL, CONE])
def test_outward_translation_error_contains_every_corner_shift(shape):
    tri = point(0, 0, 0)
    for dx in (-0.1, 0.1):
        for dy in (-0.1, 0.1):
            for dz in (-0.1, 0.1):
                assert triangle_contact(shape, tri, (dx, dy, dz), position_error_mm=0.1) is not None
    assert triangle_contact(shape, point(3, 0, 1), position_error_mm=0.1) is None


@pytest.mark.parametrize("shape", ["flat", "ball", "bull", "drill", "tapered", "chamfer", "engraving", "threadmill"])
def test_profile_producer_retains_complete_axial_pieces(shape):
    tool = ToolGeometry(4, 5, 4, 10, shape=shape, corner_radius_mm=0.5 if shape in ("bull", "tapered") else 0)
    pieces = cutting_sections(tool)
    assert pieces[0].low_mm == 0 and pieces[-1].high_mm == 5
    assert all(a.high_mm == b.low_mm for a, b in zip(pieces, pieces[1:]))
    assert all(s.radius_mm <= 2 for s in pieces)
    if shape in ("flat", "bull", "threadmill"):
        assert pieces == (AxialEnvelope("cutter", 0, 5, 2),)
    else:
        assert any(isinstance(s, RotatingShape) for s in pieces)
    for section in pieces:
        mid = (section.low_mm + section.high_mm) / 2
        assert triangle_contact(section, point(0, 0, mid)) is not None


def test_invalid_declarations_and_cancellation_fail_before_partial_witness():
    for kwargs in ({"primitive": "torus"}, {"center_mm": True}, {"center_mm": 10}, {"low_radius_mm": 1}):
        with pytest.raises(ValueError):
            RotatingShape("cutter", 0, 2, 2, **kwargs)
    with pytest.raises(InterruptedError):
        triangle_contact(BALL, point(0, 0, 1), cancelled=lambda: True)


@pytest.mark.parametrize("shape", [BALL, CONE])
@pytest.mark.parametrize(
    "start,delta",
    [
        ((-4, 0, -2), (8, 0, 0)),
        ((-4, 0, -2), (8, 0, 12)),
        ((-4, 0, -2), (8, 4, 8)),
        ((4, 1, 2), (-8, -2, -4)),
        ((2, 0, 0), (-4, 0, 2)),
        ((-1, 2, 0), (2, 0, 0)),
        ((0, 0, 0), (0, 0, 0)),
        ((0, 0, 3), (0, 0, -4)),
        ((10, -10, -10), (-20, 20, 20)),
        ((0, 0, 0), (1e-300, 0, 0)),
    ],
)
def test_whole_point_chord_matches_independent_scalar_quadratic(shape, start, delta):
    # Degenerate triangle exposes one-dimensional time minimization. Its exact
    # answer independently uses the scalar quadratic and complete cap interval.
    query_start, query_delta = start, delta
    p = (F(1), F(1), F(1))
    start, delta = tuple(F(v) for v in start), tuple(F(v) for v in delta)
    relative = tuple(p[j] - start[j] for j in range(3))
    lo, hi = F(0), F(1)
    if delta[2]:
        a, b = (relative[2] - 2) / delta[2], relative[2] / delta[2]
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    elif not 0 <= relative[2] <= 2:
        lo, hi = F(1), F(0)

    def value(t):
        x, y, z = tuple(relative[j] - t * delta[j] for j in range(3))
        return x * x + y * y + (z - 2) ** 2 - 4 if shape.primitive == "sphere" else x * x + y * y - z * z

    times = [lo, hi]
    constant, middle, end = value(F(0)), value(F(1, 2)), value(F(1))
    quadratic = 2 * (end + constant - 2 * middle)
    linear = end - constant - quadratic
    if quadratic > 0:
        times.append(max(lo, min(hi, -linear / (2 * quadratic))))
    expected = lo <= hi and min(value(t) for t in times) <= 0
    result = triangle_contact(shape, point(1, 1, 1), query_start, query_delta)
    assert (result is not None) == expected
    if result:
        assert lo <= result.sample <= hi and value(result.sample) <= 0


@pytest.mark.parametrize("flute", [0.25, 0.5])
def test_short_rounded_taper_is_clipped_to_its_declared_cutting_length(flute):
    tool = ToolGeometry(4, flute, 4, 10, shape="tapered", corner_radius_mm=1)
    sections = cutting_sections(tool)
    assert len(sections) == 1 and sections[0].high_mm == flute
    assert isinstance(sections[0], RotatingShape) and sections[0].center_mm == 1
    assert triangle_contact(sections[0], point(0, 0, flute / 2)) is not None
    assert triangle_contact(sections[0], point(1, 0, flute / 2)) is None
    assert triangle_contact(sections[0], point(0, 0, flute + 0.1)) is None
