from unittest.mock import Mock

from carveracontroller.desktop_commands import CommandPalette
from carveracontroller.desktop_components import DesktopScrollView

from .conftest import pump_frames


def test_palette_keyboard_short_results_stay_top_and_task_routes_send_no_commands(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    palette = CommandPalette(ws)
    try:
        palette.open()
        pump_frames(6)
        assert palette.input.focus
        assert isinstance(palette.scroll, DesktopScrollView)
        palette.input.text = "camera"
        pump_frames(6)
        assert len(palette.matches) >= 2
        assert palette.keydown(None, 274, None, "", [])
        pump_frames(8)
        assert palette.selected == 1
        assert palette.scroll.scroll_y == 1
        palette.input.text = "portable archive"
        pump_frames(6)
        assert len(palette.matches) == 1
        assert palette.keydown(None, 13, None, "", [])
        pump_frames(6)
        assert not palette.popup.parent
        assert ws.program_tasks.active == "Job package"
        send.assert_not_called()
        palette.open()
        pump_frames(5)
        assert palette.keydown(None, 27, None, "", [])
        pump_frames(5)
        assert not palette.popup.parent
    finally:
        palette.popup.dismiss()
        pump_frames(3)


def test_retained_inspection_action_search_opens_offline_without_commands(kivy_app, tmp_path, monkeypatch):
    from carveracontroller.desktop_commands import search_commands, workspace_commands
    from carveracontroller.machine.surface_inspection import SurfaceInspectionStore

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "surface_inspection_store", SurfaceInspectionStore(tmp_path / "empty.json"), raising=False)
    commands = workspace_commands(ws)
    matches = search_commands(commands, "inspection")
    assert matches[0].id == "inspection.records"
    assert search_commands(commands, "batch TSV")[0].id == "inspection.records"
    assert matches[0].invoke()
    pump_frames(6)
    review = ws.surface_inspection_review
    assert review.popup._is_open and "Pick a surface" in review.report.text
    assert review.batch_button.disabled
    review.popup_close()
    pump_frames(6)
    send.assert_not_called()


def test_scene_palette_routes_and_reassembly_preserve_setup_and_send_no_commands(kivy_app, monkeypatch):
    from carveracontroller.desktop_commands import workspace_commands
    from carveracontroller.machine.scene_inspection import COMPONENT_TITLES

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    commands = {c.id: c for c in workspace_commands(ws)}
    original_mode, original_selected = viewer.pose_mode, ws.object_inspector.selected
    original_distance = viewer.explosion_mm
    original_distance_text = ws.object_inspector.explode_distance.text
    setup = viewer.machine_setup
    try:
        for component in COMPONENT_TITLES:
            assert commands[f"scene.inspect.{component}"].invoke()
            pump_frames(2)
            assert ws.active_section == "Scene"
            assert ws.object_inspector.selected == component
        ws.set_pose_mode("Preview")
        ws.object_inspector.explode_distance.text = "1 in"
        assert commands["scene.explode"].invoke()
        pump_frames(4)
        assert viewer.explosion_mm == 25.4
        assert viewer.machine_setup == setup
        ws.set_pose_mode("Live")
        assert not commands["scene.explode"].invoke()
        assert viewer.explosion_offset("stock") == (0, 0, 0)
        assert commands["scene.reassemble"].invoke()
        assert viewer.explosion_mm == 0
        send.assert_not_called()
    finally:
        ws.set_pose_mode("Preview")
        viewer.set_explosion(original_distance)
        ws.set_pose_mode(original_mode)
        ws.object_inspector.select(original_selected)
        ws.object_inspector.explode_distance.text = original_distance_text
