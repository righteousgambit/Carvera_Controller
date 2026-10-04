import time
from dataclasses import replace
from unittest.mock import Mock

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    StockVolume,
    Vec3,
)
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_remedies import RemedyPanel
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.simulation_preview import simulation_tools

from .conftest import pump_frames


def panel_for(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    simulation, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    monkeypatch.setattr(
        ws.operation_panel,
        "program",
        ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X4\n"),
    )
    first = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=3, flute_length=1, stickout=10)
    alternate = replace(first, number=2, flute_length=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: first, 2: alternate})
    path = (SimulationSegment(Vec3(0, 0, 0), Vec3(4, 0, 0), "1", line=5),)
    scene = CollisionScene((CollisionObstacle("vise", AABB(Vec3(1, -1, 2), Vec3(2, 1, 3))),))
    stock = StockVolume(AABB(Vec3(0, -1, 0), Vec3(4, 1, 1)), 0.5)
    monkeypatch.setattr(simulation, "clearance_inputs", (path, simulation_tools({1: first}, {"1"}), scene, stock))
    monkeypatch.setattr(simulation, "clearance_identity", simulation._identity())
    monkeypatch.setattr(simulation, "clearance_stale", False)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = RemedyPanel(simulation, 5, "shank", "vise")
    panel.alternative.text = "T2"
    return panel, viewer, send


def wait(panel):
    deadline = time.monotonic() + 10
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running


def test_tool_and_obstacle_comparisons_are_local_and_draft_bound(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    original = panel.inputs[3].snapshot()
    panel.start()
    wait(panel)
    assert panel.comparison is not None
    assert "Selected contact: absent in candidate" in panel.result.text
    assert "captured T2 geometry" in panel.result.text
    assert "Holder geometry missing" in panel.result.text
    panel.mode.text = "Shift obstacle bounds"
    assert panel.comparison is None
    panel.shifts[1].text = "10 mm"
    panel.start()
    wait(panel)
    assert panel.comparison is not None
    assert "Selected contact: absent in candidate" in panel.result.text
    assert panel.inputs[3].snapshot() == original
    assert viewer.library_tool_table_mm[1].flute_length == 1
    send.assert_not_called()
    panel.close()


def test_alternative_outside_program_identity_cannot_change_unnoticed(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    viewer.library_tool_table_mm[2] = replace(viewer.library_tool_table_mm[2], stickout=11)
    assert panel.current()  # Program only references T1; alternative needs its own guard.
    panel.start()
    assert not panel.running
    assert panel.comparison is None
    assert "Alternative definition changed" in panel.result.text
    send.assert_not_called()
    panel.close()


def test_changed_draft_or_setup_rejects_worker_result(kivy_app, monkeypatch):
    panel, _, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    panel.alternative.text = "T1"
    wait(panel)
    assert panel.comparison is None
    assert "Draft changed during comparison" in panel.result.text
    panel.alternative.text = "T2"
    panel.start()
    monkeypatch.setattr(panel.simulation, "clearance_stale", True)
    wait(panel)
    assert panel.comparison is None
    assert "Historical result was not accepted" in panel.result.text
    send.assert_not_called()
    panel.close()


def test_alternative_change_while_worker_runs_is_rejected(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    viewer.library_tool_table_mm[2] = replace(viewer.library_tool_table_mm[2], flute_length=6)
    wait(panel)
    assert panel.current()
    assert panel.comparison is None
    assert "Alternative geometry changed during comparison" in panel.result.text
    send.assert_not_called()
    panel.close()


def test_actual_asset_identity_detects_same_path_replacement(tmp_path):
    from carveracontroller.desktop_remedies import asset_identity

    asset = tmp_path / "cutter.json"
    asset.write_bytes(b"first bytes")
    definition = ToolDefinition(2, geometry_path=str(asset))
    captured = asset_identity(definition)
    asset.write_bytes(b"other bytes")
    assert asset_identity(definition) != captured


def test_missing_choices_explain_required_input_without_starting_worker(kivy_app, monkeypatch):
    panel, _, send = panel_for(kivy_app, monkeypatch)
    panel.alternative.text = "Select loaded tool geometry"
    panel.start()
    assert "Choose a loaded alternative" in panel.result.text
    assert not panel.running
    panel.alternative.text = "T2"
    panel.target.text = "Select program tool"
    panel.start()
    assert "Choose a program tool" in panel.result.text
    assert not panel.running
    send.assert_not_called()
    panel.close()


def test_changed_contact_navigation_is_preview_only_and_rejects_stale_setup(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    wait(panel)
    comparison = panel.comparison
    assert comparison and panel.contact_actions.children
    assert "Removed contact: line 5" in panel.contact_actions.children[0].text
    inspect, seek = Mock(), Mock()
    monkeypatch.setattr(panel.simulation.workspace.operation_panel, "inspect_line", inspect)
    monkeypatch.setattr(viewer, "set_distance_by_lineidx", seek)
    panel.inspect_contact(5, comparison)
    inspect.assert_called_once_with(5, seek=False)
    seek.assert_called_once_with(5, 0)
    monkeypatch.setattr(panel.simulation, "clearance_stale", True)
    panel.inspect_contact(5, comparison)
    assert inspect.call_count == 1 and seek.call_count == 1
    assert not panel.contact_actions.children
    assert "Recompute" in panel.result.text
    send.assert_not_called()
    panel.close()
