"""Simulation launch failures preserve the last completed local review."""

from unittest.mock import Mock

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations


@pytest.mark.parametrize("calculation", ["stock", "clearance"])
@pytest.mark.parametrize("failure", [RuntimeError, OSError])
@pytest.mark.parametrize("stage", ["construct", "start"])
def test_launch_failure_restores_controls_and_preserves_results(kivy_app, monkeypatch, calculation, failure, stage):
    import carveracontroller.desktop_simulation as module

    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(viewer, "_machine_scene", lambda: {})
    monkeypatch.setattr(panel, "_alignment_key", None)
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(panel, "clearance_stale", False)
    monkeypatch.setattr(panel, "clearance_inputs", ((), {}, None, None))
    monkeypatch.setattr(panel, "clearance_identity", panel._identity())
    report, stock, context = object(), object(), object()
    monkeypatch.setattr(panel, "report", report)
    monkeypatch.setattr(panel, "rest_stock", stock)
    monkeypatch.setattr(panel, "rest_context", context)
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    monkeypatch.setattr(panel.resolution, "text", "1")
    monkeypatch.setattr(panel.artifact_status, "text", "Previous stock snapshot retained")
    candidates_parent = panel.hits.parent
    calls = Mock()
    monkeypatch.setattr(panel.hits, "set_candidates", calls)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    launched = []

    class FailedThread:
        def __init__(self, **kwargs):
            launched.append(kwargs)
            if stage == "construct":
                raise failure("private platform diagnostic")

        def start(self):
            raise failure("private platform diagnostic")

    monkeypatch.setattr(module.threading, "Thread", FailedThread)
    if calculation == "stock":
        panel.start(False)
    else:
        panel.review_clearance()
    assert [item["name"] for item in launched] == ["stock-path-review", "local-simulation"]
    assert "Stock/path review worker could not start" in panel.alignment_status.text
    assert not panel.running
    assert not panel.simulate_action.disabled
    assert not panel.clearance_action.disabled
    assert panel.cancel_action.disabled
    assert panel.report is report and panel.rest_stock is stock and panel.rest_context is context
    assert panel.artifact_status.text == "Previous stock snapshot retained"
    assert panel.hits.parent is candidates_parent
    assert "could not start" in panel.note.text
    assert "previous results preserved" in panel.note.text
    assert "private platform diagnostic" not in panel.note.text
    calls.assert_not_called()
    send.assert_not_called()
