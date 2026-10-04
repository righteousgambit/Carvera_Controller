from unittest.mock import Mock

from kivy.metrics import dp
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import displayed_control
from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.program_operations import ProgramOperations

from .conftest import pump_frames


def test_program_tasks_switch_without_discarding_drafts_or_exposing_hidden_controls(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Job")
    tasks = ws.program_tasks
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


def test_program_task_tabs_adapt_to_narrow_workbench_and_retain_single_content(kivy_app, tmp_path):
    ws = kivy_app.root.desktop_workspace
    tasks = ws.program_tasks
    parent = tasks.parent
    index = parent.children.index(tasks)
    parent.remove_widget(tasks)
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(tasks)
    popup = Popup(title="Program tasks", content=scroll, size_hint=(None, None), size=(dp(400), dp(760)))
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
        scroll.remove_widget(tasks)
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
