"""Analytic, transformed and independent-oracle checks for continuous support bounds."""

import random
from math import sqrt

import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, SweptTool, ToolGeometry, Vec3
from carveracontroller.addons.manufacturing_simulation.clearance import section_clearance
from carveracontroller.addons.manufacturing_simulation.convex_clearance import cylinder_box_clearance

TOOL = ToolGeometry(2, 2, 2, 5)


def box(a, b):
    return AABB(Vec3(*a), Vec3(*b))


def test_horizontal_axis_corner_false_positive_has_positive_narrow_gap():
    motion = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), TOOL, Vec3(1, 0, 0))
    obstacle = box((0.5, 0.8, 0.8), (1, 0.9, 0.9))
    section = motion.sections()[0]
    assert motion.section_bounds(section).intersects(obstacle)
    lower, upper, _, method, cost = section_clearance(motion, section, obstacle, 1e-5)
    expected = sqrt(2 * 0.8**2) - 1
    assert lower <= expected <= upper and upper - lower <= 1e-5
    assert "support-plane" in method and cost <= 128


@pytest.mark.parametrize("reverse", [False, True])
def test_continuous_horizontal_midmotion_witness_and_translation_invariance(reverse):
    for origin in (0, 1e6):
        a, b = Vec3(origin, -20, 0), Vec3(origin, 20, 0)
        if reverse:
            a, b = b, a
        motion = SweptTool(a, b, TOOL, Vec3(1, 0, 0))
        obstacle = box((origin + 0.5, -0.1, 4), (origin + 1, 0.1, 5))
        lo, hi, fraction, _, _ = section_clearance(motion, motion.sections()[0], obstacle, 1e-4)
        assert lo <= 3 <= hi and hi - lo <= 1e-4
        assert 0.49 < fraction < 0.51


def test_tilted_axis_broad_gap_and_contact_between_remote_endpoints():
    axis = Vec3(1 / sqrt(2), 0, 1 / sqrt(2))
    motion = SweptTool(Vec3(0, -20, 0), Vec3(0, 20, 0), TOOL, axis)
    obstacle = box((0.5, -0.01, 0.5), (0.6, 0.01, 0.6))
    lo, hi, fraction, _, cost = section_clearance(motion, motion.sections()[0], obstacle, 1e-5)
    assert lo == 0 and hi <= 1e-5 and 0.47 < fraction < 0.53 and cost <= 128
    for tip in (motion.start, motion.end):
        endpoint = SweptTool(tip, tip, TOOL, axis)
        assert section_clearance(endpoint, endpoint.sections()[0], obstacle, 1e-4)[0] > 18


def test_tangent_is_near_contact_not_false_positive_clearance():
    motion = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), TOOL, Vec3(1, 0, 0))
    lo, hi, _, method, _ = section_clearance(motion, motion.sections()[0], box((0.5, 1, -0.1), (1, 2, 0.1)), 1e-5)
    assert lo == 0 and hi < 1e-5
    assert "convex" in method


def test_budget_preserves_feasible_interval_without_claiming_tolerance():
    motion = SweptTool(Vec3(-10, 0, 0), Vec3(10, 5, 8), TOOL, Vec3(1 / sqrt(3), 1 / sqrt(3), 1 / sqrt(3)))
    result = cylinder_box_clearance(
        motion, motion.sections()[0], box((2, 12, 9), (3, 13, 10)), 1e-12, max_evaluations=2
    )
    assert result[0] <= result[1] and result[1] - result[0] > 1e-12
    assert "unresolved" in result[3] and result[4] == 2


def test_random_vertical_solver_agrees_with_independent_cylinder_time_oracle():
    rng = random.Random(196)
    for _ in range(100):
        a = Vec3(*(rng.uniform(-10, 10) for _ in range(3)))
        b = Vec3(*(rng.uniform(-10, 10) for _ in range(3)))
        low = tuple(rng.uniform(-12, 12) for _ in range(3))
        obstacle = box(low, tuple(v + rng.uniform(0.1, 3) for v in low))
        motion = SweptTool(a, b, TOOL)
        section = motion.sections()[0]
        lo, hi, *_ = cylinder_box_clearance(motion, section, obstacle, 1e-5)
        oracle_lo, oracle_hi, *_ = section_clearance(motion, section, obstacle, 1e-6)
        assert lo <= oracle_hi + 1e-8 and hi + 1e-8 >= oracle_lo
        assert hi - lo <= 1e-5

        # A signed axis permutation preserves the exact distance but exercises tilt.
        def rotate(p):
            return Vec3(p.z, p.x, p.y)

        transformed = SweptTool(rotate(a), rotate(b), TOOL, Vec3(1, 0, 0))
        rotated_box = AABB(rotate(obstacle.minimum), rotate(obstacle.maximum))
        tlo, thi, *_ = section_clearance(transformed, section, rotated_box, 1e-5)
        assert tlo <= oracle_hi + 1e-8 and thi + 1e-8 >= oracle_lo
        assert thi - tlo <= 1e-5


@pytest.mark.parametrize("tolerance", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_tolerance_rejected(tolerance):
    motion = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), TOOL)
    with pytest.raises(ValueError, match="tolerance"):
        cylinder_box_clearance(motion, motion.sections()[0], box((3, 3, 3), (4, 4, 4)), tolerance)


@pytest.mark.parametrize("budget", [True, 0, 1, 129, 2.5])
def test_invalid_budget_rejected(budget):
    motion = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), TOOL)
    with pytest.raises(ValueError, match="evaluations"):
        cylinder_box_clearance(motion, motion.sections()[0], box((3, 3, 3), (4, 4, 4)), 0.01, max_evaluations=budget)


def test_oblique_cylinders_match_analytic_horizontal_support_plane_gap():
    rng = random.Random(197)
    for _ in range(60):
        raw = tuple(rng.uniform(-1, 1) for _ in range(3))
        magnitude = sqrt(sum(x * x for x in raw))
        axis = Vec3(*(x / magnitude for x in raw))
        motion = SweptTool(Vec3(-5, -3, 10), Vec3(5, 3, 9), TOOL, axis)
        section = motion.sections()[0]
        obstacle = box((-100, -100, -1), (100, 100, 0))
        expected = 9 + min(section.low_mm * axis.z, section.high_mm * axis.z) - section.radius_mm * sqrt(1 - axis.z**2)
        lo, hi, _, _, evaluations = section_clearance(motion, section, obstacle, 1e-5)
        assert lo <= expected <= hi and hi - lo <= 1e-5 and evaluations <= 128


def test_nearly_unit_axis_is_normalized_before_bounds_and_support():
    motion = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), TOOL, Vec3(1 + 1e-9, 0, 0))
    assert motion.axis == Vec3(1, 0, 0)
    lo, hi, *_ = section_clearance(motion, motion.sections()[0], box((5, -10, -10), (6, 10, 10)), 1e-5)
    assert lo <= 3 <= hi and hi - lo <= 1e-5


def test_large_domain_and_sub_guard_precision_remain_explicitly_unresolved():
    motion = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), TOOL, Vec3(1, 0, 0))
    lo, hi, _, method, _ = section_clearance(motion, motion.sections()[0], box((10, -1, -1), (11, 1, 1)), 1e-15)
    assert lo <= 8 <= hi and hi - lo > 1e-15 and "unresolved" in method
    far = box((2e9, 0, 0), (2e9 + 1, 1, 1))
    with pytest.raises(ValueError, match="domain"):
        section_clearance(motion, motion.sections()[0], far)
