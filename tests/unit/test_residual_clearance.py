"""Ordered occupancy checks distinguish cleared cavities from future removal."""

from dataclasses import replace

import pytest

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionScene,
    SimulationSegment,
    StockVolume,
    SweptTool,
    ToolGeometry,
    Vec3,
    simulate,
)
from carveracontroller.addons.manufacturing_simulation.clearance import analyze_clearance


def setup():
    bounds = AABB(Vec3(-5, -5, 0), Vec3(5, 5, 4))
    stock = StockVolume(bounds, 0.5)
    tools = {"rough": ToolGeometry(6, 6, 6, 6), "short": ToolGeometry(2, 1, 2, 4)}
    cut = SimulationSegment(Vec3(0, 0, 0), Vec3(0, 0, 0), "rough", line=10)
    rapid = replace(cut, tool_id="short", cutting=False, line=20)
    scene = CollisionScene(stock=bounds, allowed_cut_region=bounds)
    return stock, tools, cut, rapid, scene


def test_simulation_checks_remaining_material_before_each_cut():
    stock, tools, cut, rapid, scene = setup()
    cleared = simulate((cut, rapid), tools, stock, scene)
    assert not any(line == 20 and name == "remaining stock" for line, _, name in cleared.candidates)
    stock, tools, cut, rapid, scene = setup()
    reversed_order = simulate((rapid, cut), tools, stock, scene)
    assert (20, "shank", "remaining stock") in reversed_order.candidates
    assert (20, "cutter", "remaining stock") in reversed_order.candidates
    contact = next(c for line, c in reversed_order.clearance_details if line == 20 and c.component == "shank")
    assert contact.obstacle_bounds == stock.bounds  # full initial grid is one box
    assert "center-classified" in contact.method


def test_trace_uses_starting_stock_and_does_not_mutate_caller():
    stock, tools, cut, rapid, scene = setup()
    before = stock.snapshot()
    report = analyze_clearance((cut, rapid), tools, scene, stock=stock, tolerance_mm=0.001)
    short = [p for p in report.points if p.line == 20]
    assert short and all(p.lower_mm > 0 for p in short)
    assert report.stock_resolution_mm == 0.5
    assert "before each motion" in report.stock_basis
    assert stock.snapshot() == before
    reversed_report = analyze_clearance((rapid, cut), tools, scene, stock=stock)
    assert any(p.line == 20 and p.component == "shank" and p.upper_mm == 0 for p in reversed_report.points)
    initial_bounds = analyze_clearance((cut, rapid), tools, scene)
    assert any(p.line == 20 and p.upper_mm == 0 for p in initial_bounds.points)


def test_imported_rest_stock_is_not_replaced_by_a_new_blank():
    stock, tools, cut, rapid, scene = setup()
    stock.subtract(SweptTool(cut.start, cut.end, tools["rough"]))
    restored = StockVolume.from_snapshot(stock.snapshot())
    report = analyze_clearance((rapid,), tools, scene, stock=restored)
    assert report.points and all(p.lower_mm > 0 for p in report.points)
    empty = restored.clone()
    empty._occupied[:] = bytes(empty.memory_bytes)
    empty._remaining_count = 0
    assert not analyze_clearance((rapid,), tools, scene, stock=empty).points


def test_run_boxes_preserve_occupancy_and_query_boundary_contacts():
    stock, tools, cut, _, _ = setup()
    stock.subtract(SweptTool(cut.start, cut.end, tools["rough"]))
    boxes = tuple(stock.occupied_boxes())
    assert sum(
        (b.maximum.x - b.minimum.x) * (b.maximum.y - b.minimum.y) * (b.maximum.z - b.minimum.z) for b in boxes
    ) == pytest.approx(stock.remaining_volume_mm3)
    for z in range(stock.shape[2]):
        for y in range(stock.shape[1]):
            for x in range(stock.shape[0]):
                point = stock.center(x, y, z)
                inside = any(
                    b.minimum.x <= point.x <= b.maximum.x
                    and b.minimum.y <= point.y <= b.maximum.y
                    and b.minimum.z <= point.z <= b.maximum.z
                    for b in boxes
                )
                assert inside == stock.occupied(x, y, z)
    tiny = AABB(Vec3(-5, -5, 0), Vec3(-4.5, -4.5, 0.5))
    assert tuple(stock.occupied_boxes(tiny))
    with pytest.raises(ValueError, match="budget"):
        tuple(stock.occupied_boxes(max_boxes=1))
    with pytest.raises(InterruptedError):
        tuple(stock.occupied_boxes(cancelled=lambda: True))


def test_mismatched_stock_and_cancelled_queries_are_explicit():
    stock, tools, cut, rapid, scene = setup()
    wrong = CollisionScene(stock=AABB(Vec3(0, 0, 0), Vec3(1, 1, 1)))
    with pytest.raises(ValueError, match="bounds"):
        analyze_clearance((rapid,), tools, wrong, stock=stock)
    before = stock.snapshot()
    result = simulate((cut,), tools, stock, scene, cancelled=lambda: True)
    assert result.cancelled and result.segments_processed == 0
    assert stock.snapshot() == before
