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
