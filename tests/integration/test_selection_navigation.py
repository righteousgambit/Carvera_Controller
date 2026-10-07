from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from kivy.metrics import dp
from kivy.uix.popup import Popup

from carveracontroller.desktop_bookmarks import capture_bookmark_context
from tests.integration.conftest import load_gcode_file, pump_frames


@contextmanager
def compact_program_workbench(ws):
    """Exercise the actual pane width independently of OS window minimums/density."""
    tasks = ws.program_tasks
    parent, index = tasks.parent, tasks.parent.children.index(tasks)
    parent.remove_widget(tasks)
    popup = Popup(title="Compact program workbench", content=tasks, size_hint=(None, None), size=(dp(400), dp(600)))
    popup.open()
    try:
        pump_frames(8)
        assert tasks.width < dp(420)
        yield
    finally:
        popup.dismiss()
        tasks.parent.remove_widget(tasks)
        parent.add_widget(tasks, index=index)
        pump_frames(5)


@pytest.fixture
def navigation_job(kivy_app, tmp_path, request):
    ws = kivy_app.root.desktop_workspace
    original = ws.selected_machine_profile
    ws.selected_machine_profile = {"id": "navigation-test"}
    path = tmp_path / "navigation.nc"
    path.write_text(getattr(request, "param", "G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z10\nG1 X5 F100\nG1 X10\n"))
    load_gcode_file(kivy_app, str(path))
    # The source inspector analyzes separately from the rendered path loader.
    ws.operation_panel.load(str(path))
    for _ in range(100):
        pump_frames(1, sleep=0.01)
        if ws.operation_panel.program is not None:
            break
    assert ws.operation_panel.program is not None
    ws.navigation.reset()
    yield ws, kivy_app.root.gcode_viewer
    ws.selected_machine_profile = original
    ws.navigation.reset()


def test_shared_history_restores_program_scene_selection_and_departure_framing(navigation_job, monkeypatch):
    ws, viewer = navigation_job
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.operation_panel.inspect_line(4, seek=True)
    viewer.m_xRot = viewer.m_xRotTarget = 17
    ws.object_inspector.select("workholding")
    viewer.m_xRot = viewer.m_xRotTarget = 48
    ws.object_inspector.select("fixture")
    viewer.m_xRot = viewer.m_xRotTarget = 55
    assert ws.operation_panel.history is ws.object_inspector.history is ws.navigation.history
    ws.object_inspector.navigate(-1)
    assert ws.active_section == "Scene" and ws.object_inspector.selected == "workholding"
    assert viewer.inspected_component == "workholding" and viewer.m_xRot == 48
    ws.object_inspector.navigate(-1)
    pump_frames(2)
    assert ws.active_section == "Job" and ws.operation_panel.selected_line == 4
    assert viewer.inspected_component is None and viewer.m_xRot == 17
    ws.operation_panel.navigate_history(1)
    assert ws.active_section == "Scene" and ws.object_inspector.selected == "workholding"
    assert viewer.m_xRot == 48
    ws.object_inspector.navigate(1)
    assert ws.object_inspector.selected == "fixture" and viewer.m_xRot == 55
    send.assert_not_called()


def test_operation_selection_shows_scoped_motion_facts_without_commands(navigation_job, monkeypatch, tmp_path):
    ws, viewer = navigation_job
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = ws.operation_panel
    ws.select("Job")
    ws.program_tasks.choose("Operations")
    pump_frames(8)
    operation, row = panel.rows[-1]
    row.dispatch("on_release")
    pump_frames(3)
    assert panel.selected_operation == operation
    assert panel.selected_line == operation.start_line
    pump_frames(8)
    heading_y = panel.operation_heading.to_window(panel.operation_heading.x, panel.operation_heading.top)[1]
    viewport = ws.program_tasks.scroll
    viewport_bottom = viewport.to_window(viewport.x, viewport.y)[1]
    viewport_top = viewport.to_window(viewport.x, viewport.top)[1]
    assert viewport_bottom < heading_y <= viewport_top
    assert "feed 10.0 mm" in panel.detail.text
    assert "100–100 mm/min" in panel.detail.text
    assert "does not establish stock contact" in panel.detail.text
    assert panel.detail.parent is None
    assert "Feed 10.0 mm" in panel.operation_values["path"].text
    assert panel.operation_metrics.cols == 2
    panel.operation_card.export_to_png(str(tmp_path / "operation-card-wide.png"))
    with compact_program_workbench(ws):
        assert panel.operation_metrics.cols == 1
        assert all(value.width > 0 for value in panel.operation_values.values())
        panel.operation_card.export_to_png(str(tmp_path / "operation-card-narrow.png"))
    panel.operation_details_action.dispatch("on_release")
    pump_frames(3)
    assert panel.detail.parent == panel.operation_card
    assert panel.detail.height > 0
    panel.operation_tool_actions.children[0].dispatch("on_release")
    pump_frames(3)
    assert ws.active_section == "Setup"
    assert ws.tool_comparison.selected == 1
    panel.operation_details_action.dispatch("on_release")
    assert panel.detail.parent is None
    panel.load(None)
    assert panel.operation_card.parent is None
    send.assert_not_called()


def test_tab_selection_records_one_navigation_arrival(navigation_job, monkeypatch):
    ws, _viewer = navigation_job
    enter = Mock(wraps=ws.navigation.enter)
    monkeypatch.setattr(ws.navigation, "enter", enter)
    ws.tab_buttons["Overview"].dispatch("on_release")
    assert ws.active_section == "Overview"
    enter.assert_called_once_with("Overview")


def test_navigation_timings_distinguish_callbacks_and_render_notifications(kivy_app, monkeypatch):
    from carveracontroller.desktop_ui_timing import refresh_navigation_timing

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.select("Overview")
    old = ws.navigation_timings.records[-1]
    ws.select("Settings")
    record = ws.navigation_timings.records[-1]
    assert old["superseded"]
    assert record["callback_s"] is not None and record["completed"]
    assert record["clock_turn_s"] is None and record["window_flip_s"] is None
    pump_frames(3)
    assert record["clock_turn_s"] >= record["callback_s"]
    # A real event binding is exercised explicitly: test pumping does not swap the window.
    from kivy.core.window import Window

    Window.dispatch("on_flip")
    assert record["window_flip_s"] >= record["callback_s"]
    assert {"history_depart", "history_arrive", "focus_release", "page_activation", "tab_styling"} <= set(
        record["phases_s"]
    )
    refresh_navigation_timing(ws)
    assert "callback" in ws.navigation_timing_note.text
    assert "does not prove presentation" in ws.navigation_timing_note.text
    ws.refresh(0.2)
    refresh = ws.refresh_timings.records[-1]
    assert refresh["completed"] and refresh["callback_s"] is not None
    assert {"readiness", "capabilities", "tool_comparison", "simulation_inputs"} <= set(refresh["phases_s"])
    refresh_navigation_timing(ws)
    worst = ws.refresh_timings.slowest["callback_s"]
    assert worst["callback_s"] >= refresh["callback_s"]
    assert f"Slowest session UI refresh {worst['callback_s'] * 1000:.0f} ms" in ws.navigation_timing_note.text
    send.assert_not_called()


def test_tab_switch_releases_only_outgoing_keyboard_owner_without_page_walk(kivy_app, monkeypatch):
    from kivy.uix.boxlayout import BoxLayout

    from carveracontroller.desktop_components import Field

    ws = kivy_app.root.desktop_workspace
    ws.select("Overview")
    screen = ws.inspector_pages.current_screen
    container = BoxLayout()
    field = Field(text="Uncommitted input")
    container.add_widget(field)
    screen.add_widget(container)
    pump_frames(3)
    try:
        field.focus = True
        assert field.focus
        # The old approach traversed every hidden field, label and operation.
        # A large page must not be inspected merely to find keyboard ownership.
        monkeypatch.setattr(screen, "walk", Mock(side_effect=AssertionError("whole-page focus scan")))
        ws.select("Job")
        assert not field.focus
        assert field.text == "Uncommitted input"
        toolbar = ws.tab_buttons["Preview"]
        toolbar.focus = True
        assert toolbar.focus
        ws.select("Overview")
        assert toolbar.focus  # Persistent workbench controls stay operable.
        toolbar.focus = False
    finally:
        field.focus = False
        screen.remove_widget(container)
        ws.select("Job")


@pytest.mark.parametrize(
    "navigation_job",
    ["G21 G90 G17 G91.1 G94 G54 G40 G49\nT1 M6\nG0 X0 Y0 Z10\nG1 X5 F100\nG20 G1 X1\n(comment)\n"],
    indirect=True,
)
def test_modal_inspector_filters_transitions_and_reflows_without_commands(navigation_job, monkeypatch, tmp_path):
    from kivy.core.window import Window

    ws, _viewer = navigation_job
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = ws.operation_panel
    panel.inspect_line(5, seek=True)
    panel.move_details_action.dispatch("on_release")
    pump_frames(8)
    modal = panel.modal_inspector
    assert modal.parent == panel.move_card
    assert set(modal.rows) == {"units", "feed"}
    assert modal.rows["feed"][1].text == "Before: 100 mm/min"
    assert modal.rows["feed"][2].text == "After: 100 in/min"
    try:
        modal.export_to_png(str(tmp_path / "modal-changes-wide.png"))
    except Exception as exc:
        raise AssertionError(
            {
                "modal_size": tuple(modal.size),
                "card_size": tuple(panel.move_card.size),
                "task": ws.program_tasks.active,
                "window_size": tuple(Window.size),
                "section": ws.active_section,
            }
        ) from exc
    modal.filter_action.dispatch("on_release")
    pump_frames(12)
    assert len(modal.rows) == 15
    viewport = ws.program_tasks.scroll
    filter_y = modal.filter_action.to_window(modal.filter_action.x, modal.filter_action.center_y)[1]
    bottom = viewport.to_window(viewport.x, viewport.y)[1]
    top = viewport.to_window(viewport.x, viewport.top)[1]
    assert bottom < filter_y < top
    assert "G40 · off" in modal.rows["cutter_compensation"][2].text
    with compact_program_workbench(ws):
        assert all(values.cols == 1 for values, *_ in modal.rows.values())
        assert all(entering.height > 0 and leaving.height > 0 for _, entering, leaving in modal.rows.values())
        modal.export_to_png(str(tmp_path / "modal-all-narrow.png"))
    panel.inspect_line(6)
    modal.filter_action.dispatch("on_release")
    pump_frames(12)
    assert not modal.rows and "No tracked modal changes" in modal.status.text
    filter_y = modal.filter_action.to_window(modal.filter_action.x, modal.filter_action.center_y)[1]
    assert bottom < filter_y < top
    panel.move_details_action.dispatch("on_release")
    assert modal.parent is None
    panel.load(None)
    assert modal.move is None and not modal.rows
    send.assert_not_called()


def test_changed_setup_refuses_shared_navigation_before_mutation(navigation_job, monkeypatch):
    ws, viewer = navigation_job
    ws.operation_panel.inspect_line(4, seek=True)
    ws.object_inspector.select("stock")
    original = viewer.machine_setup.stock_size_mm
    viewer.configure_machine(stock_size_mm=(12, 13, 14))
    seek = Mock()
    monkeypatch.setattr(viewer, "set_pos_by_distance", seek)
    index = ws.navigation.history.index
    try:
        assert ws.navigation.navigate(-1) is False
        assert ws.navigation.history.index == index
        assert ws.active_section == "Scene" and viewer.inspected_component == "stock"
        assert "setup changed" in ws.object_inspector.status.text
        seek.assert_not_called()
    finally:
        viewer.configure_machine(stock_size_mm=original)


def test_shared_history_branches_and_program_reload_clears_it(navigation_job):
    ws, _viewer = navigation_job
    ws.operation_panel.inspect_line(4, seek=True)
    ws.object_inspector.select("fixture")
    ws.object_inspector.select("stock")
    ws.object_inspector.navigate(-1)
    ws.object_inspector.select("atc")
    assert [point["value"] for point in ws.navigation.history.items] == [4, "fixture", "atc"]
    assert ws.operation_panel.forward_action.disabled and ws.object_inspector.forward.disabled
    ws.operation_panel.load(None)
    assert not ws.navigation.history.items
    assert ws.operation_panel.back_action.disabled and ws.object_inspector.back.disabled


def test_loaded_tool_geometry_is_bound_to_navigation_context(navigation_job):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    ws, viewer = navigation_job
    original = viewer.library_tool_table_mm
    try:
        viewer.library_tool_table_mm = {1: ToolDefinition(1, tool_type=ToolType.FLAT_END_MILL, diameter=6.35)}
        first = capture_bookmark_context(ws)
        ws.operation_panel.inspect_line(4, seek=True)
        ws.object_inspector.select("cutter")
        viewer.library_tool_table_mm[1].diameter = 3.175
        assert capture_bookmark_context(ws) != first
        assert ws.navigation.navigate(-1) is False
        assert ws.active_section == "Scene"
    finally:
        viewer.library_tool_table_mm = original


def test_generic_workbench_section_joins_same_history(navigation_job):
    ws, viewer = navigation_job
    ws.object_inspector.select("fixture")
    viewer.m_xRot = 22
    ws.select("Console")
    ws.select("Scene")
    ws.workspace_back.dispatch("on_release")
    assert ws.active_section == "Console"
    assert not ws.workspace_back.disabled and not ws.workspace_forward.disabled
    ws.workspace_back.dispatch("on_release")
    assert ws.active_section == "Scene" and ws.object_inspector.selected == "fixture"
    assert viewer.m_xRot == 22


@pytest.fixture
def compact_window(navigation_job):
    from kivy.core.window import Window

    original_size = Window.system_size
    Window.system_size = (1353, 786)
    pump_frames(5)
    yield
    Window.system_size = original_size
    pump_frames(3)


@pytest.mark.parametrize(
    "navigation_job",
    [
        "(Preview only)\nG21 G90 G17 G91.1 G94 G54 G49\nM9\nT17 M6\nS12000 M3\nG0 X0 Y0 Z0\n"
        "(Operation: Rough pocket)\nG1 X10 F600\nG1 Y10\nG1 X0\nG1 Y0\n"
        "(Operation: Finish helix)\nG1 X10\nG3 X0 Y10 Z2 I-10 J0\nG0 Z5\nM5\nM30\n"
    ],
    indirect=True,
)
def test_native_header_click_does_not_activate_clipped_program_rows(navigation_job, compact_window):
    from kivy.tests.common import UnitTestTouch

    ws, _viewer = navigation_job
    ws.operation_panel.inspect_line(8, seek=True)
    pump_frames(3)
    ws.object_inspector.select("stock")
    ws.object_inspector.select("workholding")
    pump_frames(3)

    def click(button):
        x, y = button.to_window(*button.center)
        touch = UnitTestTouch(x, y)
        touch.profile.append("button")
        touch.button = "left"
        touch.touch_down()
        pump_frames(3, sleep=0.02)
        touch.touch_up()
        pump_frames(5, sleep=0.02)

    click(ws.workspace_back)
    from kivy.core.window import Window

    assert ws.active_section == "Scene" and ws.object_inspector.selected == "stock", {
        "window_children": [(type(child).__name__, getattr(child, "title", "")) for child in Window.children],
        "button": (ws.workspace_back.pos, ws.workspace_back.size, ws.workspace_back.disabled),
        "history": (ws.navigation.history.index, ws.navigation.history.items),
        "inspector_attached": ws.inspector.parent is ws.body,
    }
    click(ws.workspace_back)
    assert ws.active_section == "Job" and ws.operation_panel.selected_line == 8
    click(ws.workspace_forward)
    assert ws.active_section == "Scene" and ws.object_inspector.selected == "stock"
    click(ws.workspace_forward)
    assert ws.active_section == "Scene" and ws.object_inspector.selected == "workholding"


def test_program_task_history_preserves_selected_line_without_late_operation_reveal(navigation_job, monkeypatch):
    ws, viewer = navigation_job
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    ws.operation_panel.inspect_line(4, seek=True)
    pump_frames(8)
    ws.program_tasks.choose("Simulation")
    pump_frames(8)
    ws.program_tasks.choose("View & playback")
    pump_frames(8)
    assert ws.navigation.history.items[-1]["task"] == "View & playback"
    count = len(ws.navigation.history.items)
    assert ws.navigation.navigate(-1)
    pump_frames(12)
    assert ws.program_tasks.active == "Simulation"
    assert ws.operation_panel.selected_line == 4
    assert len(ws.navigation.history.items) == count
    assert ws.navigation.navigate(1)
    pump_frames(12)
    assert ws.program_tasks.active == "View & playback"
    assert ws.operation_panel.selected_line == 4
    send.assert_not_called()
