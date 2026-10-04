import time
from unittest.mock import Mock

from kivy.metrics import dp
from kivy.uix.popup import Popup

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.desktop_components import displayed_control
from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.tool_history import ToolHistory

from .conftest import pump_frames


def test_program_tasks_switch_without_discarding_drafts_or_exposing_hidden_controls(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Job")
    tasks = ws.program_tasks
    ws.operation_panel._loaded(
        ws.operation_panel.generation, ProgramOperations.from_text("G21 G90 G94 G54\nG0 X0 Y0 Z2\nG1 X4 F100\n"), None
    )
    tasks.show("Operations")
    field = ws.operation_panel.search_field
    original = field.text
    field.text = "tool:T2 unresolved"
    pump_frames(5)
    assert displayed_control(field)
    field.focus = True
    tasks.buttons["Simulation"].dispatch("on_release")
    pump_frames(5)
    assert not field.focus and not displayed_control(field)
    assert tasks.sections["Operations"].parent is None
    assert tasks.sections["Simulation"].parent is tasks.host
    tasks.buttons["Job package"].dispatch("on_release")
    tasks.buttons["View & playback"].dispatch("on_release")
    tasks.buttons["Operations"].dispatch("on_release")
    pump_frames(5)
    assert field.text == "tool:T2 unresolved"
    assert len(tasks.host.children) == 1
    send.assert_not_called()
    field.text = original


def test_source_reveal_routes_from_playback_to_operations_without_machine_motion(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    operations = ws.operation_panel
    program = ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z0 F100\nG1 X4\n")
    monkeypatch.setattr(operations, "program", program)
    monkeypatch.setattr(operations, "inspector", MoveInspector(program))
    send, seek = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    ws.select("Job")
    ws.program_tasks.show("View & playback")
    operations.inspect_line(5, seek=True)
    pump_frames(12)
    assert ws.program_tasks.active == "Operations"
    assert "> 5: G1 X4" in operations.explanation.text
    seek.assert_called_once_with(5, 0)
    send.assert_not_called()


def test_move_summary_retains_uncertainty_and_details_across_navigation(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel = ws.operation_panel
    program = ProgramOperations.from_text(
        "G21 G90 G17 G91.1 G94 G54 G49\nT2 M6\nG0 X0 Y0 Z2\nG1 X10 F300 S12000 M3\n#1=2\nG1 X20\n"
    )
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    send, seek = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    panel.reset_move_card("Choose a move")
    panel.inspect_line(4, seek=False)
    assert "T2" in panel.move_values["tool"].text
    assert "300 mm/min" in panel.move_values["feed"].text
    assert "12000 RPM" in panel.move_values["spindle"].text
    assert "Machine pose unavailable" in panel.move_geometry.text
    assert panel.explanation.parent is None
    panel.move_details_action.dispatch("on_release")
    pump_frames(5)
    assert panel.explanation.parent is panel.move_card
    assert "> 4: G1 X10" in panel.explanation.text
    panel.inspect_line(6, seek=False)
    assert "Inherited uncertainty" in panel.move_issues.text
    assert "> 6: G1 X20" in panel.explanation.text
    panel.move_details_action.dispatch("on_release")
    assert panel.explanation.parent is None
    assert "Inherited uncertainty" in panel.move_issues.text
    parent, index = panel.move_card.parent, panel.move_card.parent.children.index(panel.move_card)
    parent.remove_widget(panel.move_card)
    from kivy.uix.scrollview import ScrollView

    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel.move_card)
    popup = Popup(title="Selected move", content=scroll, size_hint=(None, None), size=(dp(380), dp(700)))
    popup.open()
    try:
        pump_frames(8)
        assert panel.move_facts.cols == 1
        for item in (*panel.move_values.values(), panel.move_geometry, panel.move_issues):
            assert item.height >= item.texture_size[1]
            assert item.right <= panel.move_card.right
        panel.move_card.export_to_png(str(tmp_path / "selected-move-summary.png"))
    finally:
        popup.dismiss()
        scroll.remove_widget(panel.move_card)
        parent.add_widget(panel.move_card, index=index)
    panel.line_field.text = "999"
    panel.inspect_entry()
    assert panel.move_details_action.disabled and panel.move_facts.parent is None
    assert "Choose a source line" in panel.move_title.text
    assert panel.motion_demand.parent is None
    send.assert_not_called()
    seek.assert_not_called()


def test_selected_move_links_current_tool_context_without_commands(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel, viewer, comparison = ws.operation_panel, ws.machine.gcode_viewer, ws.tool_comparison
    program = ProgramOperations.from_text("G21 G90 G94 G54\nT2 M6\nG0 X0 Y0 Z2\nG1 X10 F300\nT3 M6\nG1 X20\n")
    monkeypatch.setattr(panel, "program", program)
    monkeypatch.setattr(panel, "inspector", MoveInspector(program))
    monkeypatch.setattr(ws.machine, "tool_history", ToolHistory())
    monkeypatch.setattr(
        viewer,
        "library_tool_table_mm",
        {2: ToolDefinition(2, diameter=6.35, stickout=30, description="Quarter-inch cutter")},
    )
    monkeypatch.setattr(viewer, "tool_table", {2: ToolDefinition(2, diameter=0.25)})
    monkeypatch.setattr(viewer, "tool_unit_scale", 25.4)
    monkeypatch.setattr(type(ws), "connected", property(lambda self: True))
    monkeypatch.setattr(
        ws.machine.controller,
        "observed_pose",
        ObservedPose(time.monotonic(), "Idle", (0, 0, 0), (0, 0, 0), 2, 50.48),
        raising=False,
    )
    send, seek = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(viewer, "set_distance_by_lineidx", seek)
    comparison.refresh(force=True)
    panel.inspect_line(4, seek=False)
    assert "library Ø 6.35 mm · CAM Ø 6.35 mm · stickout 30 mm" in panel.move_tool_context.text
    assert "reported TLO 50.48 mm" in panel.move_tool_context.text
    assert "Physical assembly identity is unverified" in panel.move_tool_context.text
    assert "Diameter discrepancy" not in panel.move_tool_context.text
    viewer.tool_table[2].diameter = 0.125
    viewer.library_tool_table_mm[2].stickout = 28
    ws.refresh(0)
    assert "CAM Ø 3.175 mm · stickout 28 mm" in panel.move_tool_context.text
    assert "Diameter discrepancy" in panel.move_tool_context.text
    monkeypatch.setattr(
        ws.machine.controller,
        "observed_pose",
        ObservedPose(time.monotonic() - 10, "Idle", (0, 0, 0), (0, 0, 0), 2, 50.48),
    )
    ws.refresh(0)
    assert "reported TLO unknown" in panel.move_tool_context.text
    assert "50.48" not in panel.move_tool_context.text
    comparison.search.text = "unrelated search"
    panel.move_tool_action.dispatch("on_release")
    pump_frames(5)
    assert ws.active_section == "Setup" and comparison.selected == 2
    assert comparison.search.text == ""
    panel.inspect_line(6, seek=False)
    assert "Tool geometry unavailable" in panel.move_tool_context.text
    panel.move_tool_action.dispatch("on_release")
    assert comparison.selected == 3
    assert "T3: no loaded geometry" in comparison.detail.text
    panel.line_field.text = "999"
    panel.inspect_entry()
    assert panel.move_tool_action.disabled and panel.move_tool_context.text == ""
    panel.review_tool_context()
    assert comparison.selected == 3
    panel.inspect_line(1, seek=False)
    assert panel.move_tool_action.disabled and panel.move_tool_action.text == "Tool selection unknown"
    panel.review_tool_context()
    assert comparison.selected == 3
    send.assert_not_called()
    seek.assert_not_called()
    comparison.selected = None


def test_long_move_review_reveals_beginning_not_bottom(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel, tasks = ws.operation_panel, ws.program_tasks
    program = ProgramOperations.from_text("G21 G90 G94 G54\nT2 M6\nG0 X0 Y0 Z2\nG1 X10 F300\n")
    panel._loaded(panel.generation, program, None)
    send, seek = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine.gcode_viewer, "set_distance_by_lineidx", seek)
    parent, index = tasks.parent, tasks.parent.children.index(tasks)
    parent.remove_widget(tasks)
    popup = Popup(title="Compact inspector", content=tasks, size_hint=(None, None), size=(dp(430), dp(600)))
    popup.open()
    try:
        pump_frames(20)
        ws.select("Job")
        tasks.show("View & playback")
        panel.inspect_line(4, seek=True)
        pump_frames(20)
        assert panel.inspection.height > tasks.scroll.height
        top = panel.history_row.to_window(panel.history_row.x, panel.history_row.top)[1]
        viewport_top = tasks.scroll.to_window(tasks.scroll.x, tasks.scroll.top)[1]
        assert abs(top - (viewport_top - dp(12))) <= dp(3)
        title_top = panel.move_title.to_window(panel.move_title.x, panel.move_title.top)[1]
        assert tasks.scroll.to_window(tasks.scroll.x, tasks.scroll.y)[1] < title_top < viewport_top
        tasks.export_to_png(str(tmp_path / "compact-inspector-start.png"))
        seek.assert_called_once_with(4, 0)
        send.assert_not_called()
    finally:
        popup.dismiss()
        tasks.parent.remove_widget(tasks)
        parent.add_widget(tasks, index=index)
        pump_frames(5)


def test_program_task_tabs_adapt_to_narrow_workbench_and_retain_single_content(kivy_app, tmp_path):
    ws = kivy_app.root.desktop_workspace
    tasks = ws.program_tasks
    parent = tasks.parent
    index = parent.children.index(tasks)
    parent.remove_widget(tasks)
    popup = Popup(title="Program tasks", content=tasks, size_hint=(None, None), size=(dp(400), dp(760)))
    popup.open()
    try:
        tasks.show("Job package")
        pump_frames(8)
        assert tasks.tabs.cols == 2
        assert all(button.right <= tasks.tabs.right + dp(1) for button in tasks.buttons.values())
        assert len(tasks.host.children) == 1
        tasks.export_to_png(str(tmp_path / "program-tasks-narrow.png"))
        popup.width = dp(850)
        pump_frames(8)
        assert tasks.tabs.cols == 4
    finally:
        popup.dismiss()
        tasks.parent.remove_widget(tasks)
        parent.add_widget(tasks, index=index)
        tasks.show("Operations")
        pump_frames(5)


def test_delayed_source_reveal_does_not_override_later_task_choice(kivy_app):
    ws = kivy_app.root.desktop_workspace
    ws.select("Job")
    tasks = ws.program_tasks
    tasks.show("Simulation")
    ws.operation_panel.queue_reveal(ws.operation_panel.inspection)
    assert tasks.active == "Operations"
    tasks.buttons["Job package"].dispatch("on_release")
    pump_frames(10)
    assert tasks.active == "Job package"
    tasks.show("Operations")


def test_delayed_source_reveal_does_not_override_later_workspace_choice(kivy_app):
    ws = kivy_app.root.desktop_workspace
    ws.select("Job")
    ws.operation_panel.queue_reveal(ws.operation_panel.inspection)
    ws.select("Scene")
    pump_frames(10)
    assert ws.active_section == "Scene"
    ws.select("Job")


def test_manual_task_choice_keeps_selector_visible_after_content_height_changes(kivy_app):
    ws = kivy_app.root.desktop_workspace
    ws.select("Job")
    tasks = ws.program_tasks
    scroll = ws.program_tools.parent
    for name in ("Job package", "View & playback", "Simulation", "Operations"):
        tasks.buttons[name].dispatch("on_release")
        pump_frames(12)
        bottom = tasks.tabs.to_window(tasks.tabs.x, tasks.tabs.y)[1]
        top = tasks.tabs.to_window(tasks.tabs.x, tasks.tabs.top)[1]
        pane_bottom = tasks.to_window(tasks.x, tasks.y)[1]
        pane_top = tasks.to_window(tasks.x, tasks.top)[1]
        assert pane_bottom <= bottom <= top <= pane_top
        assert bottom >= scroll.to_window(scroll.x, scroll.top)[1]


def test_task_navigation_remains_fixed_during_long_report_scroll(kivy_app, tmp_path):
    from kivy.uix.widget import Widget

    ws = kivy_app.root.desktop_workspace
    ws.select("Job")
    tasks = ws.program_tasks
    tasks.show("Job package")
    filler = Widget(size_hint_y=None, height=dp(2400))
    tasks.sections["Job package"].add_widget(filler)
    try:
        pump_frames(10)
        original = tasks.tabs.to_window(tasks.tabs.x, tasks.tabs.y)
        tasks.scroll.scroll_y = 0
        pump_frames(10)
        assert tasks.tabs.to_window(tasks.tabs.x, tasks.tabs.y) == original
        assert tasks.host.height > tasks.scroll.height
        tasks.export_to_png(str(tmp_path / "pinned-navigation-long-report.png"))
        ws.export_to_png(str(tmp_path / "pinned-workbench-full-layout.png"))
        assert all(displayed_control(button) for button in tasks.buttons.values())
        tasks.buttons["Operations"].dispatch("on_release")
        pump_frames(10)
        assert tasks.active == "Operations"
        assert tasks.tabs.to_window(tasks.tabs.x, tasks.tabs.y) == original
    finally:
        tasks.sections["Job package"].remove_widget(filler)
        tasks.show("Operations")
        pump_frames(5)


def test_program_action_group_wraps_without_hiding_controls(kivy_app):
    ws = kivy_app.root.desktop_workspace
    group = ws.program_actions
    original = group.width
    try:
        for width, columns in ((dp(400), 2), (dp(850), 4)):
            group.width = width
            group._trigger_layout()
            pump_frames(1)
            # The parent may restore its own width on the next frame; inspect
            # the adaptive calculation directly at the requested constraint.
            group.width = width
            group._trigger_layout()
            group.do_layout()
            assert group.cols == columns
            assert len(group.children) == 4
            assert all(child.right <= group.right + dp(1) for child in group.children)
    finally:
        group.width = original
        pump_frames(5)
