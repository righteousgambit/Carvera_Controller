import time
from dataclasses import replace
from unittest.mock import Mock

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    StockVolume,
    ToolGeometry,
    Vec3,
    simulate,
)
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations

from .conftest import pump_frames


def test_inspector_explains_captured_holder_sections_and_refuses_stale_motion(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel = ws.simulation_panel
    viewer = ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, flute_length=2, stickout=10)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(panel, "rest_identity", panel._identity())
    tool = ToolGeometry(
        2, 2, 2, 10, noncutting_sections=(AxialEnvelope("holder", 10, 12, 4, "CAD SHA256 captured-original"),)
    )
    bounds = AABB(Vec3(-1, -1, 11), Vec3(1, 1, 12))
    report = simulate(
        (SimulationSegment(Vec3(-10, 0, 0), Vec3(10, 0, 0), "1", line=5),),
        {"1": tool},
        StockVolume(AABB(Vec3(20, 20, 0), Vec3(21, 21, 1)), 1),
        CollisionScene((CollisionObstacle("vise", bounds),)),
    )
    monkeypatch.setattr(panel, "report", report)
    seek, send = Mock(), Mock()
    monkeypatch.setattr(viewer, "set_distance_by_lineidx", seek)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    popup = panel.inspect_clearance(5, "holder", "vise")
    try:
        pump_frames(8)
        labels = [w.text for w in popup.content.walk() if hasattr(w, "text")]
        assert any("10.000–12.000" in text and "captured-original" in text for text in labels)
        assert any("continuous vertical cylinder" in text for text in labels)
        assert any("physical clearance remains unqualified" in text for text in labels)
        action = next(w for w in popup.content.walk() if getattr(w, "text", "") == "Inspect motion")
        action.dispatch("on_release")
        seek.assert_called_once_with(5, 0)
        viewer.library_tool_table_mm[1] = replace(definition, stickout=11)
        action.dispatch("on_release")
        assert seek.call_count == 1
        assert any("Inputs changed" in getattr(w, "text", "") for w in popup.content.walk())
        send.assert_not_called()
    finally:
        popup.dismiss()


def test_workbench_calculation_returns_holder_unknown_and_missing_cad_error(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(viewer, "_machine_scene", lambda: {})
    monkeypatch.setattr(viewer, "set_rest_stock_geometry", Mock())
    for field, value in (
        ("rest_stock", None),
        ("report", None),
        ("rest_identity", None),
        ("rest_context", None),
        ("running", False),
    ):
        monkeypatch.setattr(panel, field, value)
    monkeypatch.setattr(panel.resolution, "text", "1")
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.start(False)
    deadline = time.monotonic() + 10
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running
    assert panel.report is not None
    assert "Holder geometry missing" in panel.note.text
    assert panel.note.height > 0
    original = panel.report
    viewer.library_tool_table_mm[1] = replace(
        definition, holder_geometry_path="/missing/holder.json", holder_geometry_sha256="expected"
    )
    panel.start(False)
    assert not panel.running
    assert "unreadable" in panel.note.text
    assert panel.report is original
    send.assert_not_called()
