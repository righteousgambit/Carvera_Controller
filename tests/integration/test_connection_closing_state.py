"""Closing is a visible transport transition, not a connection readiness claim."""


from tests.integration.conftest import pump_frames


def test_workbench_shows_closing_and_disables_connect_and_gui_motion(kivy_app, monkeypatch):
    root = kivy_app.root
    ws = root.desktop_workspace
    monkeypatch.setattr(kivy_app, "state", "Idle")
    monkeypatch.setattr(root.controller, "_closing", True)
    monkeypatch.setattr(root.controller, "_connecting", False)
    monkeypatch.setattr(root, "_wifi_connect_in_progress", False, raising=False)
    monkeypatch.setattr(root, "_usb_connect_in_progress", False, raising=False)
    monkeypatch.setattr(ws.control_owner, "binding", None)
    monkeypatch.setattr(ws, "selected_machine_profile", {"host": "test.invalid", "port": 2222})
    ws.refresh(0)
    pump_frames(2)
    assert ws._connection_opening()
    assert not ws.connected and not ws._can_connect_profile()
    assert ws.state_label.text == "Closing…"
    assert ws.connect_button.text == ws.profile_connect_button.text == "Closing…"
    assert "Closing transport" in ws.connection_health_note.text
    assert ws.profile_connect_button.disabled and ws.hold_button.disabled and ws.stop_button.disabled
