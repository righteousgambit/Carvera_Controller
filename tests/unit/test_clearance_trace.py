from math import sqrt

import pytest

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    SweptTool,
    ToolGeometry,
    Vec3,
)
from carveracontroller.addons.manufacturing_simulation.clearance import analyze_clearance, section_clearance
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.simulation_preview import simulation_segments

TOOL = ToolGeometry(2, 2, 2, 5, 6, 3)


def box(low, high):
    return AABB(Vec3(*low), Vec3(*high))


def sweep(start, end):
    return SweptTool(Vec3(*start), Vec3(*end), TOOL)


def test_clearance_interval_contains_analytic_midsegment_minimum():
    motion = sweep((-10, 0, 0), (10, 0, 0))
    obstacle = box((-0.1, 4, 0), (0.1, 5, 1))
    low, high, fraction, method, evaluations = section_clearance(motion, motion.sections()[0], obstacle, 0.001)
    assert low <= 3 <= high
    assert high - low <= 0.001
    assert 0.45 < fraction < 0.55
    assert evaluations < 40
    assert "error bound" in method


def test_vertical_gap_and_xy_gap_are_euclidean_not_minimum_axis_gap():
    motion = sweep((0, 0, 0), (0, 0, 0))
    obstacle = box((4, -0.1, 6), (5, 0.1, 7))
    low, high, fraction, _, _ = section_clearance(motion, motion.sections()[0], obstacle)
    assert low == high == 5  # radial gap 3; axial gap 4
    assert fraction == 0


@pytest.mark.parametrize("reverse", [False, True])
def test_endpoint_minimum_and_diagonal_z_motion_bound(reverse):
    motion = sweep((0, 0, 0), (10, 0, 0))
    if reverse:
        motion = SweptTool(motion.end, motion.start, TOOL)
    obstacle = box((12, -0.1, 0), (13, 0.1, 1))
    low, high, fraction, _, _ = section_clearance(motion, motion.sections()[0], obstacle, 0.0001)
    assert low <= 1 <= high
    assert high - low <= 0.0001
    assert fraction < 0.001 if reverse else fraction > 0.999
    diagonal = sweep((-5, 0, 0), (5, 0, 10))
    gap = box((-0.01, 3, 5), (0.01, 3.01, 5.01))
    lo, hi, *_ = section_clearance(diagonal, diagonal.sections()[0], gap, 0.001)
    assert lo <= 2 <= hi


def test_contact_is_zero_without_claiming_an_unobserved_contact_time():
    motion = sweep((-20, 0, 0), (20, 0, 0))
    result = section_clearance(motion, motion.sections()[0], box((0, 0, 0), (0.01, 0.01, 0.01)))
    assert result[:3] == (0, 0, None)
    assert "not localized" in result[3]


def test_tilted_geometry_has_only_lower_bound():
    motion = SweptTool(Vec3(0, 0, 0), Vec3(1, 0, 0), TOOL, Vec3(1, 0, 0))
    low, high, fraction, method, _ = section_clearance(motion, motion.sections()[0], box((10, 10, 10), (11, 11, 11)))
    assert low > 0 and high is None and fraction is None
    assert "lower bound only" in method


def test_every_component_uses_its_closest_obstacle_and_stock_policy():
    segments = (SimulationSegment(Vec3(0, 0, 0), Vec3(1, 0, 0), "1", line=8),)
    scene = CollisionScene(
        (
            CollisionObstacle("remote", box((20, 20, 0), (21, 21, 8))),
            CollisionObstacle("jaw", box((0, 4, 0), (1, 5, 8))),
        ),
        stock=box((0, 0, 0), (1, 1, 1)),
    )
    report = analyze_clearance(segments, {"1": TOOL}, scene)
    assert report.processed_segments == 1 and not report.budget_exhausted
    points = {point.component: point for point in report.points}
    assert set(points) == {"cutter", "shank", "holder"}
    assert points["cutter"].obstacle == "jaw"
    assert points["holder"].upper_mm == pytest.approx(1)
    rapid = analyze_clearance(
        (SimulationSegment(Vec3(0, 0, 0), Vec3(1, 0, 0), "1", False, line=8),), {"1": TOOL}, scene
    )
    assert next(p for p in rapid.points if p.component == "cutter").obstacle == "initial stock"
    assert next(p for p in rapid.points if p.component == "cutter").upper_mm == 0


def test_cancellation_and_budgets_never_label_partial_motion_as_examined():
    segments = tuple(SimulationSegment(Vec3(0, 0, 0), Vec3(10, 0, 0), "1", line=i) for i in range(3))
    scene = CollisionScene((CollisionObstacle("jaw", box((0, 4, 0), (1, 5, 8))),))
    stopped = analyze_clearance(segments, {"1": TOOL}, scene, cancelled=lambda: True)
    assert stopped.cancelled and stopped.processed_segments == 0 and not stopped.points
    limited = analyze_clearance(segments, {"1": TOOL}, scene, max_points=3)
    assert limited.budget_exhausted and limited.processed_segments == 1 and len(limited.points) == 3
    with pytest.raises(ValueError, match="positive"):
        analyze_clearance(segments, {"1": TOOL}, scene, tolerance_mm=0)


def test_subdivided_arc_retains_source_ratios_for_each_resolved_piece():
    program = ProgramOperations.from_text("G21 G90 G17 G91.1 G94 G54\nT1 M6\nG0 X1 Y0 Z0\nG3 X0 Y1 I-1 J0 F100\n")
    segments = simulation_segments(program)
    assert len(segments) > 1
    assert segments[0].source_start_ratio == 0
    assert segments[-1].source_end_ratio == pytest.approx(1)
    for previous, current in zip(segments, segments[1:]):
        assert previous.source_end_ratio == pytest.approx(current.source_start_ratio)
    scene = CollisionScene((CollisionObstacle("far", box((10, 10, 0), (11, 11, 1))),))
    report = analyze_clearance(segments, {"1": TOOL}, scene)
    for point in report.points:
        segment = next(s for s in segments if s.source_start_ratio <= point.source_ratio <= s.source_end_ratio)
        assert 0 <= point.source_ratio <= 1
