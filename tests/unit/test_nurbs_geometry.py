import math
import random
from bisect import bisect_right

import pytest

from carveracontroller.machine.nurbs_geometry import NurbsCurve, tessellate_nurbs


def evaluate(curve, u):
    """Independent homogeneous de Boor evaluation of the original knot vector."""
    p = curve.degree
    k = min(len(curve.weights) - 1, bisect_right(curve.knots, u) - 1)
    values = [
        [*(v * w for v in xyz), w]
        for xyz, w in zip(curve.control_points_mm[k - p : k + 1], curve.weights[k - p : k + 1])
    ]
    for r in range(1, p + 1):
        for j in range(p, r - 1, -1):
            i = k - p + j
            alpha = (u - curve.knots[i]) / (curve.knots[i + p - r + 1] - curve.knots[i])
            values[j] = [(1 - alpha) * a + alpha * b for a, b in zip(values[j - 1], values[j])]
    return tuple(v / values[p][3] for v in values[p][:3])


def check_certificate(curve, poly):
    assert poly.points_mm[0] == curve.control_points_mm[0]
    assert poly.points_mm[-1] == pytest.approx(curve.control_points_mm[-1])
    assert all(a < b for a, b in zip(poly.parameters, poly.parameters[1:]))
    assert 0 <= poly.maximum_error_bound_mm <= poly.tolerance_mm
    for i, (a, b) in enumerate(zip(poly.parameters, poly.parameters[1:])):
        for t in (0, 0.125, 0.25, 0.5, 0.75, 0.875, 1):
            exact = evaluate(curve, a + (b - a) * t)
            chord = tuple((1 - t) * x + t * y for x, y in zip(poly.points_mm[i], poly.points_mm[i + 1]))
            assert math.dist(exact, chord) <= poly.maximum_error_bound_mm + 1e-10


def test_weighted_quarter_circle_preserves_original_and_parameter_bound():
    curve = NurbsCurve.create([(1, 0, 0), (1, 1, 0), (0, 1, 0)], [1, math.sqrt(0.5), 1], [0, 0, 0, 1, 1, 1], 2)
    poly = tessellate_nurbs(curve, tolerance_mm=1e-4)
    assert curve.weights[1] == math.sqrt(0.5)
    check_certificate(curve, poly)
    for u in poly.parameters:
        x, y, _ = evaluate(curve, u)
        assert x * x + y * y == pytest.approx(1)


@pytest.mark.parametrize("degree", [1, 2, 3, 5, 8, 16])
def test_general_nonuniform_multiple_spans_against_original_deboor(degree):
    rng = random.Random(829 + degree)
    count = degree + 5
    interior = [0.1, 0.3, 0.3, 0.8] if degree > 1 else [0.1, 0.3, 0.6, 0.8]
    curve = NurbsCurve.create(
        [(rng.uniform(-10, 10), rng.uniform(-10, 10), rng.uniform(-2, 2)) for _ in range(count)],
        [rng.uniform(0.2, 3) for _ in range(count)],
        [2] * (degree + 1) + [2 + v * 5 for v in interior] + [7] * (degree + 1),
        degree,
    )
    poly = tessellate_nurbs(curve, tolerance_mm=0.02)
    check_certificate(curve, poly)
    assert poly.control_hull_bounds_mm[0] == tuple(min(p[a] for p in curve.control_points_mm) for a in range(3))


def test_straight_curve_with_nonuniform_weights_is_not_parameter_linear():
    curve = NurbsCurve.create([(0, 0, 0), (10, 0, 0)], [1, 10], [0, 0, 1, 1], 1)
    poly = tessellate_nurbs(curve, tolerance_mm=0.01)
    assert len(poly.points_mm) > 2
    check_certificate(curve, poly)


@pytest.mark.parametrize("weights", [[1, 0, 1], [1, -1, 1], [1, float("nan"), 1], [1, float("inf"), 1], [1, 1]])
def test_invalid_weights_refused(weights):
    with pytest.raises(ValueError):
        NurbsCurve.create([(0, 0, 0), (1, 1, 0), (2, 0, 0)], weights, [0, 0, 0, 1, 1, 1], 2)


@pytest.mark.parametrize(
    "knots",
    [[0, 0, 1, 1, 1, 1], [0, 0, 0, 1, 0, 1], [0, 0, 0, 0, 0, 0], [0, 0, 0, 1, 1], [0, 0, 0, float("nan"), 1, 1]],
)
def test_invalid_knots_refused(knots):
    with pytest.raises(ValueError):
        NurbsCurve.create([(0, 0, 0), (1, 1, 0), (2, 0, 0)], [1, 1, 1], knots, 2)


def test_segment_limit_cancel_precision_and_direct_dataclass_validation():
    curve = NurbsCurve.create([(0, 0, 0), (1, 10, 0), (2, 0, 0)], [1, 1, 1], [0, 0, 0, 1, 1, 1], 2)
    with pytest.raises(ValueError, match="budget"):
        tessellate_nurbs(curve, tolerance_mm=0.001, max_segments=1)
    with pytest.raises(InterruptedError):
        tessellate_nurbs(curve, tolerance_mm=0.01, cancelled=lambda: True)
    with pytest.raises(ValueError, match="allowance"):
        tessellate_nurbs(curve, tolerance_mm=1e-15)
    invalid = NurbsCurve(curve.control_points_mm, (1, 0, 1), curve.knots, 2)
    with pytest.raises(ValueError, match="positive"):
        tessellate_nurbs(invalid, tolerance_mm=0.01)


def test_weight_scale_and_parameter_domain_do_not_change_geometry():
    curve = NurbsCurve.create([(0, 0, 0), (1, 3, 0), (3, 1, 0), (4, 0, 0)], [1, 2, 3, 1], [0, 0, 0, 0.4, 1, 1, 1], 2)
    other = NurbsCurve.create(
        curve.control_points_mm, [w * 1e200 for w in curve.weights], [100 + u * 4 for u in curve.knots], 2
    )
    a = tessellate_nurbs(curve, tolerance_mm=0.01)
    b = tessellate_nurbs(other, tolerance_mm=0.01)
    assert len(a.points_mm) == len(b.points_mm)
    for x, y in zip(a.points_mm, b.points_mm):
        assert x == pytest.approx(y)
    check_certificate(other, b)


def test_seeded_weighted_nonuniform_curves_preserve_all_sampled_interval_bounds():
    rng = random.Random(51183)
    for _ in range(100):
        degree = rng.randint(1, 6)
        interiors = sorted(rng.sample(range(1, 99), rng.randint(0, 5)))
        count = degree + 1 + len(interiors)
        curve = NurbsCurve.create(
            [(rng.uniform(-100, 100), rng.uniform(-100, 100), rng.uniform(-10, 10)) for _ in range(count)],
            [rng.uniform(0.05, 10) for _ in range(count)],
            [0] * (degree + 1) + [u / 100 for u in interiors] + [1] * (degree + 1),
            degree,
        )
        check_certificate(curve, tessellate_nurbs(curve, tolerance_mm=0.1))


@pytest.mark.parametrize("tolerance", [0, -1, float("nan"), float("inf"), True])
def test_invalid_conversion_tolerance(tolerance):
    curve = NurbsCurve.create([(0, 0, 0), (1, 0, 0)], [1, 1], [0, 0, 1, 1], 1)
    with pytest.raises(ValueError):
        tessellate_nurbs(curve, tolerance_mm=tolerance)


@pytest.mark.parametrize("budget", [0, -1, 100001, 1.2, True])
def test_invalid_conversion_budget(budget):
    curve = NurbsCurve.create([(0, 0, 0), (1, 0, 0)], [1, 1], [0, 0, 1, 1], 1)
    with pytest.raises(ValueError):
        tessellate_nurbs(curve, tolerance_mm=0.01, max_segments=budget)


def test_knot_insertion_is_cancelled_before_subdivision():
    curve = NurbsCurve.create([(0, 0, 0), (1, 3, 0), (3, 1, 0), (4, 0, 0)], [1, 2, 3, 1], [0, 0, 0, 0.4, 1, 1, 1], 2)
    with pytest.raises(InterruptedError):
        tessellate_nurbs(curve, tolerance_mm=0.01, cancelled=lambda: True)


def test_extreme_weight_ratio_and_parameter_condition_refuse_false_precision():
    points = [(0, 0, 0), (1, 0, 0)]
    curve = NurbsCurve.create(points, [1e-200, 1], [0, 0, 1, 1], 1)
    with pytest.raises(ValueError, match="weight ratio"):
        tessellate_nurbs(curve, tolerance_mm=0.01)
    curve = NurbsCurve.create(points, [1, 1], [1e15, 1e15, 1e15 + 1, 1e15 + 1], 1)
    with pytest.raises(ValueError, match="allowance"):
        tessellate_nurbs(curve, tolerance_mm=0.01)
