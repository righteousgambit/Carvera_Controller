from unittest.mock import Mock

from carveracontroller.desktop_components import displayed_control
from tests.integration.conftest import pump_frames


def test_choose_program_remains_reachable_with_collapsed_details(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(kivy_app, "playing", False)
    monkeypatch.setattr(kivy_app, "state", "Idle")
    monkeypatch.setattr(kivy_app, "selected_local_filename", "")
    monkeypatch.setattr(kivy_app, "selected_remote_filename", "")
    ws.select("Job")
    ws._sync_program_actions()
    card = ws.program_context
    original = card.expanded
    choose = ws.program_action_buttons["Choose program"]
    monkeypatch.setattr(choose, "disabled", False)
    try:
        if card.expanded:
            card.toggle()
        pump_frames(8)
        assert choose.parent is ws.program_summary and displayed_control(choose)
        choose.focus = True
        ws._sync_program_actions()
        assert choose.focus and not card.expanded
        choose.dispatch("on_release")
        pump_frames(8)
        assert ws.program_browser.popup.parent is not None
        ws.program_browser.dismiss()
        pump_frames(8)
        assert not kivy_app.selected_local_filename and not kivy_app.selected_remote_filename
        send.assert_not_called()
    finally:
        if getattr(ws, "program_browser", None):
            ws.program_browser.dismiss()
        if card.expanded != original:
            card.toggle()
