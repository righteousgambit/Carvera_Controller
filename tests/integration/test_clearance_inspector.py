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
    monkeypatch.setattr(panel, "clearance_identity", panel._identity())
    monkeypatch.setattr(panel, "clearance_stale", False)
    monkeypatch.setattr(panel, "rest_identity", None)  # Navigation belongs to the capture, not a loaded stock snapshot.
    inspect = Mock()
    monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
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
    was_open = panel.details_open
    popup = panel.inspect_clearance(5, "holder", "vise")
    try:
        pump_frames(8)
        assert popup.parent is panel.content
        assert panel.details_open
        assert panel.clearance_return.parent is ws.operation_panel.inspection
        labels = [w.text for w in popup.walk() if hasattr(w, "text")]
        assert any("10.000–12.000" in text and "captured-original" in text for text in labels)
        assert any("continuous vertical cylinder" in text for text in labels)
        assert any("physical clearance remains unqualified" in text for text in labels)
        action = next(w for w in popup.walk() if getattr(w, "text", "") == "Show motion in preview")
        assert not action.disabled
        action.dispatch("on_release")
        seek.assert_called_once_with(5, 0)
        inspect.assert_called_once_with(5, seek=False)
        assert panel.clearance_inspector is popup  # Seeking retains the local review.
        reveal = Mock()
        monkeypatch.setattr(ws.operation_panel, "_reveal", reveal)
        panel.clearance_return.dispatch("on_release")
        pump_frames(8)
        reveal.assert_called_with(popup.children[-1])
        assert seek.call_count == 1
        viewer.library_tool_table_mm[1] = replace(definition, stickout=11)
        action.dispatch("on_release")
        assert seek.call_count == 1
        assert action.disabled
        assert any("Inputs changed" in getattr(w, "text", "") for w in popup.walk())
        send.assert_not_called()
    finally:
        panel.close_clearance_inspector()
    assert panel.clearance_inspector is None
    assert panel.clearance_return is None
    historical = panel.inspect_clearance(5, "holder", "vise")
    try:
        assert any("Historical captured inputs" in getattr(w, "text", "") for w in historical.walk())
        action = next(w for w in historical.walk() if getattr(w, "text", "") == "Show motion in preview")
        assert action.disabled
        action.dispatch("on_release")
        assert seek.call_count == 1
    finally:
        panel.close_clearance_inspector()
        if panel.details_open != was_open:
            panel.toggle_details()
        pump_frames(8)


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


def test_replacing_docked_review_cancels_prior_comparison_and_keeps_one_return(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel = ws.simulation_panel
    monkeypatch.setattr(panel, "report", Mock(clearance_details=()))
    was_open = panel.details_open
    first = panel.inspect_clearance(5, "shank", "vise")
    old_remedies, old_return = panel.clearance_remedies, panel.clearance_return
    second = panel.inspect_clearance(6, "holder", "vise")
    try:
        pump_frames(8)
        assert first.parent is None
        assert old_remedies.cancel_event.is_set()
        assert old_return.parent is None
        assert second.parent is panel.content
        assert panel.clearance_return.parent is ws.operation_panel.inspection
        assert panel.clearance_remedies.contact_actions.height == 0
    finally:
        panel.close_clearance_inspector()
        if panel.details_open != was_open:
            panel.toggle_details()
        pump_frames(8)
