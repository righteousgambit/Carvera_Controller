import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.simulation_preview import (
    simulation_segments,
    simulation_tool_issues,
    simulation_tools,
    stock_geometry,
    stock_path_review,
)


def test_resolved_segments_exclude_unknown_initial_travel_and_convert_inches():
    program = ProgramOperations.from_text("G20 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0.1\nG1 Z0 F10\nG1 X1\n")
    segments = simulation_segments(program)
    assert len(segments) == 2
    assert segments[-1].end.x == pytest.approx(25.4)
    assert program.unresolved_motion_lines == (3,)
    tools = simulation_tools(
        {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=3, flute_length=5, stickout=10)}, {"1"}
    )
    assert tools["1"].overall_length_mm == 10


def test_simulation_rejects_missing_reach_or_multiple_wcs():
    with pytest.raises(ValueError, match="stickout"):
        simulation_tools({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2)}, {"1"})
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z1\nG1 X1 F100\nG55\nG0 X0 Y0 Z1\nG1 X1\n"
    )
    with pytest.raises(ValueError, match="Multiple work offsets"):
        simulation_segments(program)


def test_tool_preflight_reports_all_missing_and_incomplete_envelopes():
    definitions = {
        2: ToolDefinition(2, ToolType.DRILL, diameter=5, shank_diameter=6.35, flute_length=15, stickout=20),
        3: ToolDefinition(3, ToolType.THREAD_MILL, diameter=3),
    }
    issues = dict(simulation_tool_issues(definitions, {"2", "3", "4"}))
    assert set(issues) == {"3", "4"}
    assert "stickout" in issues["3"] and "explicit profile" in issues["4"]
    definitions[3] = ToolDefinition(
        3, ToolType.THREAD_MILL, diameter=3, shank_diameter=6.35, flute_length=2, stickout=12
    )
    assert simulation_tool_issues(definitions, {"2", "3"}) == ()


def test_tool_preflight_does_not_read_cad_on_ui_refresh(monkeypatch):
    from unittest.mock import Mock

    import carveracontroller.machine.simulation_preview as preview

    envelope = Mock(side_effect=OSError("missing asset"))
    monkeypatch.setattr(preview, "assembly_envelopes", envelope)
    definition = ToolDefinition(2, ToolType.DRILL, diameter=5, shank_diameter=6.35, flute_length=15, stickout=20)
    assert simulation_tool_issues({2: definition}, {"2"}) == ()
    envelope.assert_not_called()
    with pytest.raises(OSError, match="missing asset"):
        simulation_tools({2: definition}, {"2"})
    envelope.assert_called_once()


def test_generated_drill_and_thread_program_removes_stock_with_explicit_tools():
    from carveracontroller.addons.manufacturing_simulation import CollisionScene, simulate
    from carveracontroller.machine.hole_planning import Hole, HoleTool, HoleWorkflow, ThreadSpec

    workflow = HoleWorkflow(
        (Hole(10, 20, 8, 6),),
        {"drill": HoleTool(2, "drill", 5.1054, 15, 20), "threadmill": HoleTool(3, "threadmill", 3, 2, 12)},
        ThreadSpec.named("1/4-20"),
        5,
        0,
        -15,
        200,
        80,
        12000,
    )
    program = ProgramOperations.from_text(workflow.plan().gcode())
    definitions = {
        2: ToolDefinition(2, ToolType.DRILL, diameter=5.1054, shank_diameter=6.35, flute_length=15, stickout=20),
        3: ToolDefinition(3, ToolType.THREAD_MILL, diameter=3, shank_diameter=6.35, flute_length=2, stickout=12),
    }
    segments = simulation_segments(program)
    tools = simulation_tools(definitions, {segment.tool_id for segment in segments})
    stock = StockVolume(AABB(Vec3(5, 15, -8), Vec3(15, 25, 0)), 1)
    report = simulate(segments, tools, stock, CollisionScene(stock=stock.bounds))
    assert report.removed_volume_mm3 > 0
    assert report.remaining_volume_mm3 < 800
    assert not report.cancelled
    assert "thread grooves" in tools["3"].stock_model_note
    assert not any(
        line in program.unresolved_motion_lines
        for line, text in enumerate(program.lines, 1)
        if text.startswith(("G2 ", "G3 "))
    )


def test_rest_geometry_exposes_boundary_without_interior_cell_faces():
    stock = StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 1, 1)), 1)
    geometry = stock_geometry(stock)
    assert len(geometry.indices) == 10 * 6
    assert min(geometry.vertices[0::10]) == 0
    assert max(geometry.vertices[0::10]) == 2
    with pytest.raises(ValueError, match="face budget"):
        stock_geometry(stock, max_faces=1)


def test_stock_alignment_checks_continuous_cutting_envelope_not_tip_or_path_box():
    from carveracontroller.addons.manufacturing_simulation import SimulationSegment, ToolGeometry

    tool = ToolGeometry(2, 4, 2, 5)
    stock = AABB(Vec3(0, 0, 0), Vec3(2, 2, 2))
    # Tooltip stays below stock, but exposed flute crosses its side.
    side = SimulationSegment(Vec3(-3, 1, -1), Vec3(3, 1, -1), "1", True, line=7)
    review = stock_path_review((side,), {"1": tool}, stock)
    assert review["possible_overlap_lines"] == (7,)
    assert review["stock_minimum_mm"] == (0, 0, 0)
    # Diagonal's bounding box includes stock; its actual cylinder misses.
    diagonal = SimulationSegment(Vec3(-5, 1, 0), Vec3(1, 5, 0), "1", True, line=8)
    assert stock_path_review((diagonal,), {"1": tool}, stock)["possible_overlap_segments"] == 0
    rapid = SimulationSegment(Vec3(1, 1, 0), Vec3(1, 1, 1), "1", False, line=9)
    assert stock_path_review((rapid,), {"1": tool}, stock)["cutting_segments"] == 0
    high = SimulationSegment(Vec3(1, 1, 3), Vec3(1, 1, 4), "1", True, line=10)
    assert stock_path_review((high,), {"1": tool}, stock)["possible_overlap_segments"] == 0


@pytest.mark.parametrize("angle", [45, 90, -30])
def test_rotated_rest_stock_faces_match_exact_grid_transform(angle):
    from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3

    bounds = AABB(Vec3(0, 0, 0), Vec3(4, 2, 2))
    original = StockVolume(bounds, 1)
    rotated = StockVolume(bounds, 1, rotation_deg=angle, pivot=Vec3(-4, 7, 0))
    plain, posed = stock_geometry(original), stock_geometry(rotated)
    assert plain.indices == posed.indices
    for offset in range(0, len(plain.vertices), 10):
        expected = rotated.program_point(Vec3(*plain.vertices[offset : offset + 3]))
        normal = rotated.program_direction(Vec3(*plain.vertices[offset + 3 : offset + 6]))
        assert posed.vertices[offset : offset + 3] == pytest.approx(expected.tuple)
        assert posed.vertices[offset + 3 : offset + 6] == pytest.approx(normal.tuple)
