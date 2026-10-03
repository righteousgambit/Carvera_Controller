import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.simulation_preview import simulation_segments, simulation_tools, stock_geometry


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


def test_rest_geometry_exposes_boundary_without_interior_cell_faces():
    stock = StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 1, 1)), 1)
    geometry = stock_geometry(stock)
    assert len(geometry.indices) == 10 * 6
    assert min(geometry.vertices[0::10]) == 0
    assert max(geometry.vertices[0::10]) == 2
    with pytest.raises(ValueError, match="face budget"):
        stock_geometry(stock, max_faces=1)
