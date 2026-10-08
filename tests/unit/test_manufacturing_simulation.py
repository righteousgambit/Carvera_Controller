"""Machining geometry truth: continuous sweeps, volume, and rotary pivots."""

from math import radians, tan

import pytest

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    Joint,
    MachineKinematics,
    StockVolume,
    SweptTool,
    ToolGeometry,
    Transform,
    Vec3,
)


def box(lo, hi):
    return AABB(Vec3(*lo), Vec3(*hi))


def tool(shape="flat"):
    return ToolGeometry(2, 4, 2, 10, 6, 4, shape)


def test_swept_holder_collision_between_endpoints():
    scene = CollisionScene(
        (CollisionObstacle("vise", box((-1, -1, 11), (1, 1, 12))),), registration_confirmed=True, geometry_complete=True
    )
    result = scene.check_sweep(SweptTool(Vec3(-10, 0, 0), Vec3(10, 0, 0), tool()))
    assert result.candidates == (("holder", "vise"),)
    assert result.status == "potential_collision"
    assert not result.qualified


def test_clear_and_unknown_registration():
    sweep = SweptTool(Vec3(0, 0, 0), Vec3(1, 0, 0), tool())
    scene = CollisionScene((CollisionObstacle("remote", box((20, 20, 20), (21, 21, 21))),))
    assert scene.check_sweep(sweep).status == "unknown"
    scene.registration_confirmed = scene.geometry_complete = True
    assert scene.check_sweep(sweep).status == "clear_conservative_bounds"


def test_permission_never_allows_shank_or_rapid_stock_contact():
    scene = CollisionScene(stock=box((-2, -2, 0), (2, 2, 8)), allowed_cut_region=box((-10, -10, -10), (10, 10, 20)))
    sweep = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 1), tool())
    assert ("shank", "stock") in scene.check_sweep(sweep).candidates
    assert ("cutter", "stock") in scene.check_sweep(sweep, cutting=False).candidates


def test_subtraction_real_volume_and_idempotence():
    stock = StockVolume(box((0, 0, 0), (10, 10, 4)), 0.5)
    sweep = SweptTool(Vec3(-2, 5, 0), Vec3(12, 5, 0), tool())
    before = stock.remaining_volume_mm3
    result = stock.subtract(sweep)
    assert 70 < result.removed_volume_mm3 < 90
    assert result.remaining_volume_mm3 + result.removed_volume_mm3 == pytest.approx(before)
    assert stock.subtract(sweep).removed_volume_mm3 == 0
    assert len(stock.boundary_boxes()) > 0


def test_long_sweep_no_timestep_holes():
    stock = StockVolume(box((0, 0, 0), (100, 2, 1)), 0.5)
    stock.subtract(SweptTool(Vec3(-100, 1, 0), Vec3(200, 1, 0), tool()))
    assert stock.remaining_volume_mm3 == 0


def test_diagonal_sweep_height_coupled_to_xy():
    stock = StockVolume(box((0, 0, 0), (10, 2, 10)), 0.5)
    stock.subtract(SweptTool(Vec3(0, 1, 0), Vec3(10, 1, 10), tool()))
    assert stock.occupied(0, 1, 19)
    assert not stock.occupied(10, 1, 10)


def test_ball_round_bottom_and_rest_material():
    bounds = box((-2, -2, 0), (2, 2, 4))
    flat, ball = StockVolume(bounds, 0.25), StockVolume(bounds, 0.25)
    flat.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool()))
    ball.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool("ball")))
    assert flat.removed_volume_mm3 > ball.removed_volume_mm3 > 0
    comparison = ball.compare_target(flat)
    assert comparison["rest_volume_mm3"] > 0
    assert comparison["gouge_volume_mm3"] == 0


def test_budget_and_tilted_continuous_cut():
    with pytest.raises(ValueError, match="budget"):
        StockVolume(box((0, 0, 0), (10, 10, 10)), 0.01)
    stock = StockVolume(box((0, 0, 0), (4, 2, 2)), 0.25)
    result = stock.subtract(SweptTool(Vec3(0, 1, 1), Vec3(0, 1, 1), tool(), Vec3(1, 0, 0)))
    assert 12 < result.removed_volume_mm3 < 14
    assert stock.occupied(1, 0, 0)
    assert not stock.occupied(1, 3, 3)


def test_pivot_and_inverse():
    transform = Transform.rotation_about(Vec3(0, 0, 1), 90, Vec3(10, 0, 0))
    assert transform.apply(Vec3(11, 0, 0)).tuple == pytest.approx((10, 1, 0))
    point = Vec3(5, 8, 3)
    assert transform.inverse().apply(transform.apply(point)).tuple == pytest.approx(point.tuple)


def test_five_axis_forward_and_limits():
    machine = MachineKinematics(
        tool_chain=(
            Joint("X", "linear", Vec3(1, 0, 0), -100, 100),
            Joint("Z", "linear", Vec3(0, 0, 1), -100, 100),
            Joint("B", "rotary", Vec3(0, 1, 0), -90, 90),
        ),
        work_chain=(Joint("A", "rotary", Vec3(1, 0, 0), -180, 180), Joint("C", "rotary", Vec3(0, 0, 1), -360, 360)),
    )
    pose = machine.forward({"X": 10, "Z": 20, "B": 90, "A": 0, "C": 90}, 5)
    assert pose.tooltip_world.tuple == pytest.approx((5, 0, 20))
    assert pose.tooltip_work.tuple == pytest.approx((0, -5, 20))
    assert pose.axis_in_work.tuple == pytest.approx((0, -1, 0), abs=1e-8)
    assert not pose.controller_tcp_supported
    assert not pose.limit_violations
    invalid = machine.forward({"X": 101, "Z": 20, "B": 0, "A": 0, "C": 0})
    assert invalid.limit_violations == ("X",)
    assert pose.transform_tool_mesh((Vec3(0, 0, -5),))[0] == pose.tooltip_world


def test_bad_state_and_reflection_rejected():
    machine = MachineKinematics((Joint("X", "linear", Vec3(1, 0, 0), -1, 1),))
    with pytest.raises(ValueError, match="mismatch"):
        machine.forward({})
    with pytest.raises(ValueError, match="right handed"):
        Transform((-1, 0, 0, 0, 1, 0, 0, 0, 1))


def test_program_orchestration_cancel_and_tool_resolution():
    from carveracontroller.addons.manufacturing_simulation import SimulationSegment, simulate

    stock = StockVolume(box((0, 0, 0), (10, 2, 1)), 0.5)
    segments = [
        SimulationSegment(Vec3(-2, 1, 0), Vec3(12, 1, 0), "T1", line=4),
        SimulationSegment(Vec3(0, 1, 0), Vec3(10, 1, 0), "T1", line=5),
    ]
    progress = []
    result = simulate(
        segments,
        {"T1": tool()},
        stock,
        CollisionScene(),
        progress=lambda *args: progress.append(args),
        cancelled=lambda: bool(progress),
    )
    assert result.cancelled and result.segments_processed == 1
    assert result.removed_volume_mm3 == 20
    assert result.status == "cancelled"
    with pytest.raises(ValueError, match="Missing geometry"):
        simulate(segments, {}, stock, CollisionScene())


def test_inverse_kinematics_convergence_unreachable_and_unwind():
    from carveracontroller.addons.manufacturing_simulation import inverse_kinematics, unwind_rotary

    machine = MachineKinematics(
        tool_chain=(
            Joint("X", "linear", Vec3(1, 0, 0), -100, 100),
            Joint("Y", "linear", Vec3(0, 1, 0), -100, 100),
            Joint("Z", "linear", Vec3(0, 0, 1), -100, 100),
            Joint("B", "rotary", Vec3(0, 1, 0), -90, 90),
            Joint("C", "rotary", Vec3(0, 0, 1), -720, 720),
        )
    )
    seed = {"X": 0, "Y": 0, "Z": 0, "B": 0, "C": 0}
    result = inverse_kinematics(machine, Vec3(10, 15, 25), seed, 5, Vec3(0.5, 0, 3**0.5 / 2))
    assert result.converged
    assert result.tip_error_mm < 0.01
    assert result.axis_error < 0.001
    assert machine.forward(result.positions, 5).tooltip_work.tuple == pytest.approx((10, 15, 25), abs=0.01)
    impossible = inverse_kinematics(machine, Vec3(1000, 0, 0), seed, max_iterations=10)
    assert not impossible.converged
    desired = dict(seed, C=350)
    assert unwind_rotary(machine, desired, dict(seed, C=-20))["C"] == -10


def test_stock_snapshot_carries_residual_and_integrity():
    stock = StockVolume(box((0, 0, 0), (5, 5, 2)), 0.5)
    stock.subtract(SweptTool(Vec3(0, 1, 0), Vec3(5, 1, 0), tool()))
    snapshot = stock.snapshot()
    restored = StockVolume.from_snapshot(snapshot)
    assert restored.remaining_volume_mm3 == stock.remaining_volume_mm3
    assert restored.top_surface() == stock.top_surface()
    copied = stock.clone()
    copied.subtract(SweptTool(Vec3(0, 4, 0), Vec3(5, 4, 0), tool()))
    assert copied.remaining_volume_mm3 < stock.remaining_volume_mm3
    snapshot["occupancy_sha256"] = "bad"
    with pytest.raises(ValueError, match="integrity"):
        StockVolume.from_snapshot(snapshot)


def test_bull_profile_rounds_only_outer_bottom_corner():
    cutter = ToolGeometry(4, 4, 4, 10, shape="bull", corner_radius_mm=0.5)
    assert cutter.axial_radius(0) == pytest.approx(1.5)
    assert cutter.axial_radius(0.5) == pytest.approx(2)
    assert cutter.axial_radius(0.25) == pytest.approx(1.5 + (0.25 - 0.25**2) ** 0.5)
    stock = StockVolume(box((-2, -2, 0), (2, 2, 4)), 0.1)
    flat = stock.clone()
    stock.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), cutter))
    flat.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), ToolGeometry(4, 4, 4, 10)))
    assert stock.removed_volume_mm3 < flat.removed_volume_mm3
    assert stock.occupied(39, 20, 0)
    assert not stock.occupied(20, 20, 0)


@pytest.mark.parametrize("shape", ["drill", "chamfer", "engraving", "tapered"])
def test_conical_profiles_have_sloping_removal(shape):
    cutter = ToolGeometry(4, 4, 4, 10, shape=shape, tip_angle_deg=90, taper_angle_deg=45)
    assert cutter.axial_radius(0) == 0
    assert cutter.axial_radius(1) == pytest.approx(1)
    assert cutter.axial_radius(3) == pytest.approx(2)
    stock = StockVolume(box((-2, -2, 0), (2, 2, 4)), 0.25)
    stock.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), cutter))
    assert stock.occupied(14, 8, 0)
    assert not stock.occupied(14, 8, 12)


def test_cone_continuous_long_and_tilted_sweeps():
    cutter = ToolGeometry(2, 4, 2, 10, shape="chamfer", taper_angle_deg=45)
    stock = StockVolume(box((0, 0, 0.5), (100, 1, 1)), 0.25)
    stock.subtract(SweptTool(Vec3(-100, 0.5, 0), Vec3(200, 0.5, 0), cutter))
    assert stock.remaining_volume_mm3 == 0
    tilted = StockVolume(box((0, 0, 0), (4, 2, 2)), 0.25)
    result = tilted.subtract(SweptTool(Vec3(0, 1, 1), Vec3(0, 1, 1), cutter, Vec3(1, 0, 0)))
    assert result.removed_volume_mm3 > 0
    assert tilted.occupied(0, 0, 0)
    assert not tilted.occupied(10, 3, 3)


def test_threadmill_envelope_and_profile_validation():
    thread = ToolGeometry(2, 4, 2, 10, shape="threadmill")
    stock = StockVolume(box((-2, -2, 0), (2, 2, 4)), 0.5)
    flat = stock.clone()
    stock.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), thread))
    flat.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool()))
    assert stock.remaining_volume_mm3 == flat.remaining_volume_mm3
    with pytest.raises(ValueError, match="Corner"):
        ToolGeometry(2, 4, 2, 10, shape="bull", corner_radius_mm=2)
    with pytest.raises(ValueError, match="angle"):
        ToolGeometry(2, 4, 2, 10, shape="drill", tip_angle_deg=180)


def test_conical_diagonal_sweep_hits_between_clear_endpoints():
    cutter = ToolGeometry(4, 4, 4, 10, shape="drill", tip_angle_deg=90)
    stock = StockVolume(box((-0.1, -0.1, 1.4), (0.1, 0.1, 1.6)), 0.1)
    result = stock.subtract(SweptTool(Vec3(-5, 0, 0), Vec3(5, 0, 2), cutter))
    assert result.removed_voxels == stock.memory_bytes
    assert stock.remaining_volume_mm3 == 0


def test_tapered_ball_tip_and_finite_cutting_reach():
    cutter = ToolGeometry(4, 4, 4, 10, shape="tapered", corner_radius_mm=0.5, taper_angle_deg=10)
    assert cutter.axial_radius(0) == 0
    assert cutter.axial_radius(0.5) == pytest.approx(0.5)
    assert cutter.axial_radius(1.5) == pytest.approx(0.5 + tan(radians(10)))
    assert cutter.axial_radius(4.01) == 0
    stock = StockVolume(box((-1, -1, 5), (1, 1, 6)), 0.25)
    assert stock.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), cutter)).removed_voxels == 0


@pytest.mark.parametrize("angle", [90, 37, -125])
def test_oriented_stock_cut_matches_rotated_program_and_preserves_volume(angle):
    bounds = box((2, -1, 0), (12, 3, 4))
    pivot = Vec3(-3, 7, 0)
    flat = StockVolume(bounds, 0.5)
    rotated = StockVolume(bounds, 0.5, rotation_deg=angle, pivot=pivot)
    start, end = Vec3(0, 1, 0), Vec3(14, 1, 0)
    flat.subtract(SweptTool(start, end, tool()))
    rotated.subtract(SweptTool(rotated.program_point(start), rotated.program_point(end), tool()))
    assert rotated._occupied == flat._occupied
    assert rotated.remaining_volume_mm3 == pytest.approx(flat.remaining_volume_mm3)
    assert rotated.removed_volume_mm3 == pytest.approx(flat.removed_volume_mm3)
    assert rotated.remaining_volume_mm3 + rotated.removed_volume_mm3 == pytest.approx(160)
    assert rotated.center(0, 0, 0) == rotated.program_point(flat.center(0, 0, 0))
    restored = StockVolume.from_snapshot(rotated.snapshot())
    assert restored.grid_bounds == bounds
    assert restored.rotation_deg == pytest.approx(angle)
    assert restored.pivot == pivot
    assert restored._occupied == rotated._occupied
    assert restored.center(0, 0, 0) == rotated.center(0, 0, 0)
    clone = rotated.clone()
    assert clone.compare_target(rotated)["rest_volume_mm3"] == 0
    with pytest.raises(ValueError, match="identical grids"):
        rotated.compare_target(flat)
    clone._occupied[0] = 0
    assert clone._occupied is not rotated._occupied


def test_oriented_stock_occupancy_boxes_contain_all_transformed_cells():
    stock = StockVolume(box((0, 0, 0), (4, 2, 2)), 1, rotation_deg=45)
    stock.subtract(SweptTool(stock.center(0, 0, 0), stock.center(0, 0, 0), tool()))
    boxes = tuple(stock.occupied_boxes())
    for z in range(stock.shape[2]):
        for y in range(stock.shape[1]):
            for x in range(stock.shape[0]):
                if stock.occupied(x, y, z):
                    point = stock.center(x, y, z)
                    assert any(
                        all(lo <= p <= hi for lo, p, hi in zip(b.minimum.tuple, point.tuple, b.maximum.tuple))
                        for b in boxes
                    )
    assert stock.boundary_boxes()
    assert StockVolume(box((0, 0, 0), (4, 2, 2))).snapshot()["schema"] == 1


@pytest.mark.parametrize("angle", [True, float("nan"), float("inf"), "90"])
def test_invalid_stock_rotation_is_rejected(angle):
    with pytest.raises(ValueError, match="rotation"):
        StockVolume(box((0, 0, 0), (4, 2, 2)), rotation_deg=angle)


@pytest.mark.parametrize("shape", ["flat", "ball", "bull"])
def test_cancelled_removal_retains_exact_previous_stock_and_can_resume(shape):
    stock = StockVolume(box((0, 0, 0), (10, 10, 4)), 0.25)
    cutter = tool("flat" if shape == "bull" else shape)
    if shape == "bull":
        from dataclasses import replace

        cutter = replace(cutter, shape="bull", corner_radius_mm=0.25)
    sweep = SweptTool(Vec3(-2, 5, 0), Vec3(12, 5, 0), cutter)
    before = bytes(stock._occupied), stock.remaining_volume_mm3
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 4

    with pytest.raises(InterruptedError, match="Stock removal cancelled"):
        stock.subtract(sweep, cancelled=cancelled)
    assert calls == 4
    assert (bytes(stock._occupied), stock.remaining_volume_mm3) == before
    expected = stock.clone()
    result = stock.subtract(sweep, cancelled=lambda: False)
    reference = expected.subtract(sweep)
    assert result == reference
    assert result.removed_voxels > 0
    assert bytes(stock._occupied) == bytes(expected._occupied)


def test_cancelled_simulation_removal_reports_only_completed_segments(monkeypatch):
    from carveracontroller.addons.manufacturing_simulation import SimulationSegment, simulate
    from carveracontroller.addons.manufacturing_simulation.geometry import CollisionResult

    stock = StockVolume(box((0, 0, 0), (10, 10, 4)), 0.25)
    expected = stock.clone()
    segments = [SimulationSegment(Vec3(-2, y, 0), Vec3(12, y, 0), "T1", line=line) for y, line in [(2, 10), (7, 20)]]
    expected.subtract(SweptTool(segments[0].start, segments[0].end, tool()))
    scene = CollisionScene((), registration_confirmed=True, geometry_complete=True)
    # Isolate cancellation during subtraction after the clearance stage completes.
    monkeypatch.setattr(scene, "check_sweep", lambda *_a, **_k: CollisionResult((("holder", "vise"),), True, True))
    original = stock.subtract
    removed = 0

    def subtract(sweep, *, cancelled=None):
        nonlocal removed
        removed += 1
        if removed == 1:
            return original(sweep, cancelled=cancelled)
        calls = 0

        def during_removal():
            nonlocal calls
            calls += 1
            return calls >= 4

        return original(sweep, cancelled=during_removal)

    monkeypatch.setattr(stock, "subtract", subtract)
    progress = []
    report = simulate(segments, {"T1": tool()}, stock, scene, progress=lambda *row: progress.append(row))
    assert report.cancelled and report.status == "cancelled"
    assert report.segments_processed == 1
    assert report.candidates == ((10, "holder", "vise"),)
    assert [row[1] for row in progress] == [10]
    assert report.remaining_volume_mm3 == expected.remaining_volume_mm3
    assert bytes(stock._occupied) == bytes(expected._occupied)


def test_cancellation_at_stock_publication_preserves_all_cells():
    stock = StockVolume(box((0, 0, 0), (2, 2, 1)), 1)
    sweep = SweptTool(Vec3(-2, 1, 0), Vec3(4, 1, 0), tool())
    before = bytes(stock._occupied), stock.remaining_volume_mm3
    calls = 0

    def cancel_before_publication():
        nonlocal calls
        calls += 1
        return calls == 3  # Initial, first candidate, then publication.

    with pytest.raises(InterruptedError):
        stock.subtract(sweep, cancelled=cancel_before_publication)
    assert calls == 3
    assert (bytes(stock._occupied), stock.remaining_volume_mm3) == before
    assert stock.subtract(sweep).removed_voxels == 4
