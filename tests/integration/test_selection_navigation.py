from unittest.mock import Mock

import pytest

from carveracontroller.desktop_bookmarks import capture_bookmark_context
from tests.integration.conftest import load_gcode_file, pump_frames


@pytest.fixture
def navigation_job(kivy_app, tmp_path):
    ws = kivy_app.root.desktop_workspace
    original = ws.selected_machine_profile
    ws.selected_machine_profile = {"id": "navigation-test"}
    path = tmp_path / "navigation.nc"
    path.write_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z10\nG1 X5 F100\nG1 X10\n")
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
