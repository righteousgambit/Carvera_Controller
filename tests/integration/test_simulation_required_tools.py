"""Simulation keeps every scoped cutter review reachable after geometry is ready."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from kivy.config import Config
from kivy.metrics import dp

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_view_state import capture_view
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames, set_window_viewport
from tests.integration.test_completed_program_source import until
from tests.integration.test_simulation_cutter_assignment import assignment as _assignment
from tests.integration.test_simulation_cutter_assignment import wait

assignment = _assignment


def ready_tool(number, name="Saved cutter", diameter=3):
    return ToolDefinition(
        number,
        ToolType.FLAT_END_MILL,
        description=name,
        diameter=diameter,
        shank_diameter=6,
        flute_length=12,
        stickout=20,
    )


def rows(panel):
    return {int(action.text.split()[1][1:]): action for action in panel.tool_remedies.children}


def test_ready_rows_follow_exact_operation_scope_and_changed_definitions(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel, operations, viewer = ws.simulation_panel, ws.operation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z0 F100\n(operation: Finish)\nT3 M6\nG1 X1\nT9 M6\n"
    )
    first, second = (
        next(
            operation
            for operation in program.operations
            if program.motion_tool_ids(operation.start_line, operation.end_line) == {number}
        )
        for number in (1, 3)
    )
    monkeypatch.setattr(operations, "program", program)
    monkeypatch.setattr(operations, "selected_operation", None)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=None))
    monkeypatch.setattr(
        viewer,
        "library_tool_table_mm",
        {1: ready_tool(1, "Rougher", 6), 3: ready_tool(3, "Finisher"), 9: ready_tool(9, "Unused")},
    )
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(panel, "artifact_transfer", None)
    monkeypatch.setattr(panel.scope, "text", "Whole program")
    send, calculate, review = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(panel, "start", calculate)
    monkeypatch.setattr(panel, "review_simulation_tool", review)
    panel.refresh_controls()
    assert set(rows(panel)) == {1, 3}
    assert "Rougher · nominal Ø 6 mm" in rows(panel)[1].text
    assert "Finisher · nominal Ø 3 mm" in rows(panel)[3].text
    assert not panel.simulate_action.disabled

    panel.scope.text = "Selected operation"
    assert not rows(panel) and panel.simulate_action.disabled
    assert "Choose an operation" in panel.tool_readiness.text
    for operation, number in ((first, 1), (second, 3), (first, 1)):
        operations.selected_operation = operation
        panel.refresh_controls()
        assert set(rows(panel)) == {number}
        assert panel._tool_issues == () and not panel.simulate_action.disabled
    viewer.library_tool_table_mm[1] = replace(viewer.library_tool_table_mm[1], description="Replacement", diameter=4)
    panel.refresh_controls()
    assert "Replacement · nominal Ø 4 mm" in rows(panel)[1].text
    retained = rows(panel)[1]
    for _ in range(10):
        panel.refresh_controls()
    assert rows(panel)[1] is retained
    retained.dispatch("on_release")
    review.assert_called_once_with(1)
    del viewer.library_tool_table_mm[1]
    panel.refresh_controls()
    assert panel.simulate_action.disabled and "Load an explicit profile" in rows(panel)[1].text
    operations.selected_operation = None
    panel.refresh_controls()
    assert not rows(panel)
    panel.scope.text = "Whole program"
    assert set(rows(panel)) == {1, 3}
    operations.program = None
    panel.refresh_controls()
    assert not rows(panel) and panel.simulate_action.disabled
    calculate.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("state", ("missing", "unsupported", "unknown"))
def test_unready_or_unknown_motion_keeps_existing_calculation_gate(kivy_app, monkeypatch, state):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\n" + ("" if state == "unknown" else "T3 M6\n") + "G0 X0 Y0 Z2\nG1 Z0 F100\n"
    )
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(ws.operation_panel, "selected_operation", None)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=None))
    monkeypatch.setattr(
        viewer,
        "library_tool_table_mm",
        {3: replace(ready_tool(3), tool_type=ToolType.UNKNOWN)} if state == "unsupported" else {},
    )
    monkeypatch.setattr(panel.scope, "text", "Whole program")
    panel.refresh_controls()
    assert panel._tool_issues and panel.simulate_action.disabled
    if state == "unknown":
        assert not rows(panel)
        assert "no declared tool" in panel.tool_readiness.text
    else:
        assert set(rows(panel)) == {3}
        reason = panel._tool_issues[0][1]
        assert reason in rows(panel)[3].text
        assert "Cutting dimensions ready" not in rows(panel)[3].text


@pytest.mark.parametrize("width", (780, 1600))
def test_required_tool_rows_wrap_without_clipping_long_names(kivy_app, monkeypatch, tmp_path, width):
    from kivy.core.window import Window

    ws = kivy_app.root.desktop_workspace
    panel = ws.simulation_panel
    program = ProgramOperations.from_text("G21 G90 G94 G54\nT3 M6\nG0 X0 Y0 Z2\nG1 Z0 F100\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(ws.operation_panel, "selected_operation", None)
    monkeypatch.setattr(ws.machine.gcode_viewer, "machine_setup", MachineSetup(stock_size_mm=None))
    monkeypatch.setattr(
        ws.machine.gcode_viewer,
        "library_tool_table_mm",
        {3: ready_tool(3, "Long saved finishing cutter name with holder and extended catalog description")},
    )
    previous_size = (Window.width, Window.height)
    expanded = panel.details_open
    try:
        set_window_viewport(width, 960)
        ws.select("Job")
        ws.program_tasks.show("Simulation")
        if not panel.details_open:
            panel.toggle_details()
        panel.scope.text = "Whole program"
        panel.refresh_controls()
        pump_frames(6)
        action = rows(panel)[3]
        assert panel.content.parent is panel
        assert "Review T3 geometry" in action.text and "nominal Ø 3 mm" in action.text
        assert action.texture_size[0] <= action.width
        assert action.height >= action.texture_size[1] + dp(16)
        assert action.height <= panel.tool_remedies.height
        assert action.right <= panel.tool_remedies.right + dp(1)
        kivy_app.root.export_to_png(str(tmp_path / f"simulation-required-tools-{width}.png"))
    finally:
        if panel.details_open != expanded:
            panel.toggle_details()
        set_window_viewport(*previous_size)
        pump_frames(3)


def test_ready_review_button_reopens_real_assignment_and_returns_updated_cutter(assignment, monkeypatch):
    f = assignment
    panel = f.ws.simulation_panel
    expanded = panel.details_open
    if not panel.details_open:
        panel.toggle_details()
    pump_frames(4)
    f.ws.program_tasks.scroll.scroll_y = 0.4
    original, operation, line = (
        f.viewer.library_tool_table_mm[1],
        f.ws.operation_panel.selected_operation,
        f.ws.operation_panel.selected_line,
    )
    view, scope = capture_view(f.viewer), panel.scope.text
    stored, preferences = f.store.path.read_bytes(), dict(Config.items("carvera"))
    calculate = Mock()
    monkeypatch.setattr(panel, "start", calculate)
    try:
        for profile in (f.chosen, f.first):
            panel.refresh_controls()
            assert set(rows(panel)) == {3}
            assert panel.details_open and panel.content.parent is panel
            assert rows(panel)[3].parent is panel.tool_remedies
            rows(panel)[3].dispatch("on_release")
            context = f.ws.simulation_tool_assignment
            assert context is not None and context.active and context.number == 3
            assert f.ws.tool_comparison.library_action.text == "Choose cutter for T3"
            f.ws.tool_comparison.library_action.dispatch("on_release")
            assert f.ws.active_section == "Profiles" and f.library.simulation_assignment is context
            f.library.select_record("tools", profile["id"])
            f.library.apply_button.dispatch("on_release")
            wait(f)
            until(lambda context=context: not context.active, "Simulation return did not settle")
            assert f.ws.active_section == "Job" and f.ws.program_tasks.active == "Simulation"
            assert f.ws.operation_panel.selected_operation is operation and f.ws.operation_panel.selected_line == line
            assert panel.details_open and panel.content.parent is panel
            assert panel.scope.text == scope and f.ws.program_tasks.scroll.scroll_y == pytest.approx(0.4)
            assert capture_view(f.viewer) == view
            assert f.viewer.library_tool_table_mm[1] == original
            assert f.viewer.library_tool_table_mm[3].diameter == profile["diameter"]
            assert profile["name"] in rows(panel)[3].text
            assert "Cutting dimensions ready" in rows(panel)[3].text
            assert panel._tool_issues == () and not panel.simulate_action.disabled
        assert f.store.path.read_bytes() == stored and dict(Config.items("carvera")) == preferences
        assert f.chosen["number"] == f.first["number"] == 1
        assert f.app.playing is False
        f.write.assert_not_called()
        f.commands.assert_not_called()
        calculate.assert_not_called()
    finally:
        if panel.details_open != expanded:
            panel.toggle_details()
