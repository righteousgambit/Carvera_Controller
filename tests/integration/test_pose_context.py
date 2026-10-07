import time
from unittest.mock import Mock

import pytest

from carveracontroller.machine.observed_pose import ObservedPose
from tests.integration.conftest import load_gcode_file, pump_frames


@pytest.fixture
def pose_job(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    root = ws.machine
    viewer = root.gcode_viewer
    path = tmp_path / "pose-context.nc"
    path.write_text(
        "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z10\n"
        "(Operation: Rough pocket)\nG1 Z0 F100\nG1 X10\n"
        "(Operation: Finish wall)\nG1 Y5 F200\nG1 X0\n"
    )
    previous_filename = ws.app.selected_local_filename
    ws.app.selected_local_filename = str(path)
    load_gcode_file(kivy_app, str(path))
    viewer.set_machine_visible(True)
    viewer.restore_default_view()
    ws.operation_panel.load(str(path))
    for _ in range(100):
        pump_frames(1, sleep=0.01)
        if ws.operation_panel.program is not None:
            break
    assert ws.operation_panel.program is not None
    previous = ws.app.state
    root.config_loaded = True
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    monkeypatch.setattr(root.controller, "observed_pose", None)
    ws.app.state = "Idle"
    yield ws, viewer, send
    root.gcode_playing = False
    viewer.dynamic_display = False
    ws.set_pose_mode("Preview")
    ws.app.state = previous
    ws.app.selected_local_filename = previous_filename


def fresh_pose():
    return ObservedPose(time.monotonic(), "Idle", (-190, -125, -100), (1, 2, 3), 1, 40)


def test_operation_inspection_leaves_live_and_identifies_preview(pose_job, monkeypatch, tmp_path):
    ws, viewer, send = pose_job
    monkeypatch.setattr(ws.machine.controller, "observed_pose", fresh_pose())
    ws.set_pose_mode("Live")
    operation = ws.operation_panel.program.operations[-1]
    ws.operation_panel.select(operation)
    pump_frames(2)
    ws.refresh(0)
    assert viewer.pose_mode == ws.pose_choice.text == "Preview"
    assert ws.operation_panel.selected_operation == operation
    assert "Finish wall" in ws.pose_status.text
    assert f"line {operation.start_line}" in ws.pose_status.text
    assert "Preview" in ws.model_caption.text
    row = next(row for item, row in ws.operation_panel.rows if item == operation)
    assert "\nT1" in row.text
    assert f"lines {operation.start_line}–{operation.end_line}" in row.text.casefold()
    ws.select("Job")
    pump_frames(3)
    ws.export_to_png(str(tmp_path / "operation-preview-context.png"))
    ws.operation_panel._reveal(ws.operation_panel.items, align_top=True)
    pump_frames(8)
    ws.export_to_png(str(tmp_path / "operation-cards.png"))
    from kivy.core.window import Window
    from kivy.metrics import dp

    original_size = Window.size
    try:
        Window.size = (1100, 850)
        pump_frames(8)
        for _operation, card in ws.operation_panel.rows:
            assert card.height >= card.texture_size[1] + dp(16)
        assert ws.return_live_action.right <= ws.inspector.right
        ws.export_to_png(str(tmp_path / "operation-cards-narrow.png"))
    finally:
        Window.size = original_size
        pump_frames(3)
    send.assert_not_called()


def test_return_live_stops_only_local_animation_and_retains_inspection(pose_job, monkeypatch):
    ws, viewer, send = pose_job
    ws.operation_panel.select(ws.operation_panel.program.operations[-1])
    selected = ws.operation_panel.selected_line
    preview_distance = viewer.display_count
    monkeypatch.setattr(ws.machine.controller, "observed_pose", fresh_pose())
    ws.machine.gcode_playing = True
    viewer.dynamic_display = True
    playing = ws.app.playing
    assert ws.return_to_live()
    assert viewer.pose_mode == ws.pose_choice.text == "Live"
    assert not ws.machine.gcode_playing and not viewer.dynamic_display
    assert ws.app.playing == playing
    assert ws.operation_panel.selected_line == selected
    assert viewer.display_count == preview_distance
    assert "fresh reported pose" in ws.pose_status.text
    send.assert_not_called()


def test_stale_or_disconnected_packet_cannot_return_live(pose_job, monkeypatch):
    ws, viewer, send = pose_job
    stale = ObservedPose(time.monotonic() - 2, "Idle", (-190, -125, -100), (1, 2, 3), 1, 40)
    monkeypatch.setattr(ws.machine.controller, "observed_pose", stale)
    assert not ws.return_to_live()
    assert viewer.pose_mode == "Preview" and ws.return_live_action.disabled
    ws.set_pose_mode("Live")
    assert "stale / unavailable" in ws.pose_status.text
    monkeypatch.setattr(ws.machine.controller, "observed_pose", fresh_pose())
    ws.app.state = "Disconnected"
    ws.enter_preview()
    assert not ws.return_to_live()
    assert viewer.pose_mode == "Preview" and viewer.observed_pose is None
    send.assert_not_called()


def test_compare_survives_inspection_and_playback_enters_preview(pose_job):
    ws, viewer, send = pose_job
    ws.set_pose_mode("Compare")
    ws.operation_panel.select(ws.operation_panel.program.operations[-1])
    assert viewer.pose_mode == ws.pose_choice.text == "Compare"
    assert "live marker unavailable" in ws.pose_status.text
    ws.set_pose_mode("Live")
    ws.machine.gcode_play_toggle()
    assert viewer.pose_mode == ws.pose_choice.text == "Preview"
    assert ws.machine.gcode_playing
    ws.machine.gcode_play_toggle()
    ws.set_pose_mode("Live")
    ws.machine.gcode_play_to_start()
    assert viewer.pose_mode == ws.pose_choice.text == "Preview"
    send.assert_not_called()


def test_empty_operation_workspace_hides_program_controls_and_restores_them(pose_job, tmp_path):
    ws, _viewer, send = pose_job
    panel = ws.operation_panel
    program = panel.program
    assert panel.inspection_tools.parent is panel
    assert not panel.bank_toggle.disabled
    panel.toggle_banks()
    assert panel.bank_workbench.parent is panel
    panel.load(None)
    pump_frames(3)
    assert panel.inspection_tools.parent is None
    assert panel.bank_workbench.parent is None
    assert panel.bank_toggle.disabled
    assert panel.bank_toggle.text == "+ Prepare tool banks"
    assert not panel.items.data
    assert not panel.rows
    assert panel.items.height == 0
    assert panel.items.layout_manager is not None
    assert "Choose a local program" in panel.note.text
    panel.export_to_png(str(tmp_path / "operations-empty.png"))
    generation = panel.generation
    panel._loaded(generation - 1, program, None)
    assert panel.inspection_tools.parent is None
    panel._loaded(generation, program, None)
    pump_frames(3)
    assert panel.inspection_tools.parent is panel
    assert not panel.bank_toggle.disabled
    assert len(panel.rows) == len(program.operations)
    assert sum(child is panel.inspection_tools for child in panel.children) == 1
    panel.load(None)
    panel._loaded(panel.generation, None, "file could not be read")
    assert panel.inspection_tools.parent is None
    assert panel.bank_toggle.disabled
    assert "file could not be read" in panel.note.text
    send.assert_not_called()


@pytest.mark.parametrize("machine_visible", [True, False])
def test_static_cutter_uses_live_pose_and_retains_compare_cursor(pose_job, monkeypatch, machine_visible):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    ws, viewer, send = pose_job
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=40)})
    viewer.select_preview_tool(1)
    monkeypatch.setattr(viewer, "lengths", None)
    monkeypatch.setattr(viewer, "raw_tools", [])
    pose = fresh_pose()
    monkeypatch.setattr(ws.machine.controller, "observed_pose", pose)
    viewer.set_machine_visible(machine_visible)
    table_motion = lambda: viewer._machine_pose["table"][1] if machine_visible else 0
    try:
        ws.set_pose_mode("Live")
        viewer._on_frame_tick(0)
        point = viewer.machine_setup.work_point(pose.machine_mm)
        scale = viewer.move_scale_by_positon or 1
        expected = tuple(
            (point[i] + (table_motion() if i == 1 else 0)) * scale - viewer.lines_center[i] for i in range(3)
        )
        assert tuple(viewer.pointermesh["offset"]) == pytest.approx(expected)
        viewer._preview_program_point = (7, 8, 9)
        ws.set_pose_mode("Compare")
        viewer._on_frame_tick(0)
        assert viewer._preview_program_point == (7, 8, 9)
        expected = tuple(
            ((7, 8, 9)[i] + (table_motion() if i == 1 else 0)) * scale - viewer.lines_center[i] for i in range(3)
        )
        assert tuple(viewer.pointermesh["offset"]) == pytest.approx(expected)
        viewer.set_pose_mode("Live")
        viewer.set_observed_pose(None)
        viewer._on_frame_tick(0)
        assert tuple(viewer.pointermesh["offset"]) == (1e6, 1e6, 1e6)
        send.assert_not_called()
    finally:
        viewer.select_preview_tool(None)
        viewer.load_tool_profiles({})
        viewer.set_machine_visible(True)


def test_static_live_follow_program_uses_known_reported_tool_without_cam(pose_job, monkeypatch):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    ws, viewer, send = pose_job
    monkeypatch.setattr(viewer, "lengths", None)
    monkeypatch.setattr(viewer, "raw_tools", [])
    viewer.load_tool_profiles({1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, length=40)})
    viewer.select_preview_tool(None)
    monkeypatch.setattr(ws.machine.controller, "observed_pose", fresh_pose())
    try:
        ws.set_pose_mode("Live")
        viewer._on_frame_tick(0)
        assert viewer.preview_tool_override is None
        assert viewer._active_tool_number == 1
        assert len(viewer.pointer_mesh_instrs) == 2
        assert all(mesh.indices for mesh in viewer.pointer_mesh_instrs)
        viewer.set_observed_pose(ObservedPose(time.monotonic(), "Idle", (-190, -125, -100), (1, 2, 3), 99, 40))
        viewer._on_frame_tick(0)
        assert viewer.pointer_mesh_instrs == []
        assert viewer._active_tool_number is None
        viewer.set_observed_pose(fresh_pose())
        viewer._on_frame_tick(0)
        assert viewer._active_tool_number == 1
        assert len(viewer.pointer_mesh_instrs) == 2
        viewer.set_observed_pose(None)
        viewer._on_frame_tick(0)
        assert tuple(viewer.pointermesh["offset"]) == (1e6, 1e6, 1e6)
        send.assert_not_called()
    finally:
        viewer.set_pose_mode("Preview")
        viewer.select_preview_tool(None)
        viewer.load_tool_profiles({})
