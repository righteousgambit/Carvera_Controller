import math
from bisect import bisect_right

import pytest

from carveracontroller.machine.spline_geometry import tessellate_cubic


def bernstein(controls, t):
    weights = ((1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t**2 * (1 - t), t**3)
    return tuple(sum(weights[i] * controls[i][axis] for i in range(4)) for axis in range(3))


@pytest.mark.parametrize(
    "controls",
    [
        ((0, 0, 0), (0, 20, 0), (30, -20, 0), (30, 0, 0)),
        ((0, 0, 0), (100, 0, 0), (-100, 0, 0), (1, 0, 0)),
        ((0, 0, 0), (20, 10, 5), (-20, 10, -5), (0, 0, 0)),
        ((100000, -200000, 5), (100001, -199990, 6), (100002, -200010, 7), (100003, -200000, 8)),
    ],
)
def test_parameter_matched_bound_covers_s_shape_reversal_loop_and_large_origin(controls):
    path = tessellate_cubic(controls, tolerance_mm=0.01)
    assert path.points_mm[0] == controls[0] and path.points_mm[-1] == controls[-1]
    assert path.parameters[0] == 0 and path.parameters[-1] == 1
    assert all(a < b for a, b in zip(path.parameters, path.parameters[1:]))
    assert 0 < path.maximum_error_bound_mm <= path.tolerance_mm
    assert len(path.points_mm) > 2
    for index in range(1001):
        t = index / 1000
        interval = min(bisect_right(path.parameters, t) - 1, len(path.parameters) - 2)
        a, b = path.parameters[interval : interval + 2]
        fraction = (t - a) / (b - a)
        linear = tuple(
            start + (end - start) * fraction
            for start, end in zip(path.points_mm[interval], path.points_mm[interval + 1])
        )
        exact = bernstein(controls, t)
        assert math.dist(exact, linear) <= path.maximum_error_bound_mm
        assert all(
            lo <= value <= hi
            for lo, value, hi in zip(*[path.control_hull_bounds_mm[0], exact, path.control_hull_bounds_mm[1]])
        )


def test_known_straight_curve_needs_one_segment_and_controls_remain_immutable():
    controls = [[0, 0, 0], [1, 2, 3], [2, 4, 6], [3, 6, 9]]
    path = tessellate_cubic(controls, tolerance_mm=0.001, max_segments=1)
    assert path.points_mm == ((0, 0, 0), (3, 6, 9))
    assert path.parameters == (0, 1)
    controls[0][0] = 99
    assert path.points_mm[0] == (0, 0, 0)


def test_budget_refuses_complete_conversion_instead_of_truncating():
    with pytest.raises(ValueError, match="segment budget"):
        tessellate_cubic(((0, 0, 0), (0, 100, 0), (100, -100, 0), (100, 0, 0)), tolerance_mm=0.001, max_segments=2)


def test_cancellation_is_checked_during_subdivision():
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 4

    with pytest.raises(InterruptedError):
        tessellate_cubic(((0, 0, 0), (0, 100, 0), (100, -100, 0), (100, 0, 0)), tolerance_mm=0.001, cancelled=cancel)
    assert calls == 4


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, 1e-20])
def test_invalid_or_unrepresentable_tolerance_refused(value):
    with pytest.raises(ValueError):
        tessellate_cubic(((0, 0, 0), (1, 2, 0), (2, 1, 0), (3, 0, 0)), tolerance_mm=value)


@pytest.mark.parametrize("budget", [0, True, 1.5, 100001])
def test_invalid_budget_refused(budget):
    with pytest.raises(ValueError):
        tessellate_cubic(((0, 0, 0), (1, 2, 0), (2, 1, 0), (3, 0, 0)), tolerance_mm=0.01, max_segments=budget)


@pytest.mark.parametrize("point", [(0, 0), (True, 0, 0), (float("nan"), 0, 0), (1000001, 0, 0)])
def test_invalid_control_point_refused(point):
    with pytest.raises(ValueError):
        tessellate_cubic((point, (1, 2, 0), (2, 1, 0), (3, 0, 0)), tolerance_mm=0.01)
