from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("fresh_response,busy", [(True, False), (False, False), (False, True)])
def test_ui_delay_and_command_activity_do_not_replace_received_machine_evidence(
    kivy_app, monkeypatch, fresh_response, busy
):
    from carveracontroller import main as module

    root = kivy_app.root
    controller = root.controller
    monkeypatch.setattr(module.time, "monotonic", lambda: 100)
    monkeypatch.setattr(root, "heartbeat_time", module.time.time() - 30 if fresh_response else module.time.time())
    for name, value in (
        ("stream", Mock()),
        ("_last_status_received_at", 99.8 if fresh_response else 90),
        ("_connection_started_at", 80),
        ("_refresh_heartbeat", False),
        ("_heartbeat_grace_until", 0),
        ("_connecting", False),
        ("_baud_switch_in_progress", False),
        ("sendNUM", 10 if busy else 0),
        ("loadNUM", 0),
    ):
        monkeypatch.setattr(controller, name, value)
    for name in (
        "uploading",
        "downloading",
        "file_just_loaded",
        "_wifi_connect_in_progress",
        "_usb_connect_in_progress",
    ):
        monkeypatch.setattr(root, name, False, raising=False)
    monkeypatch.setattr(root, "reconnection_popup", Mock(_is_open=True))
    close = Mock()
    monkeypatch.setattr(controller, "close", close)
    monkeypatch.setattr(root, "updateStatus", Mock())
    root.blink_state()
    if fresh_response:
        close.assert_not_called()
        root.updateStatus.assert_not_called()
    else:
        close.assert_called_once_with()
        root.updateStatus.assert_called_once_with()


def test_connection_health_separates_received_status_from_ui_interval(kivy_app, monkeypatch):
    from carveracontroller import desktop_workspace as module

    root = kivy_app.root
    workspace = root.desktop_workspace
    monkeypatch.setattr(module.time, "monotonic", lambda: 100)
    monkeypatch.setattr(workspace, "_last_ui_refresh_at", 88, raising=False)
    monkeypatch.setattr(workspace, "_largest_ui_refresh_gap", 0, raising=False)
    monkeypatch.setattr(root.controller, "machine_response_age", lambda _: 0.2)
    monkeypatch.setattr(root, "_wifi_connect_in_progress", True, raising=False)
    monkeypatch.setattr(root.controller, "executeCommand", Mock())
    workspace.refresh(0)
    assert workspace.receive_age_metric.value.text == "0.20s"
    assert workspace.ui_gap_metric.value.text == "12.00s"
    assert "12.00s" in workspace.ui_gap_metric.detail.text
    assert workspace.state_label.text == "Connecting…"
    root.controller.executeCommand.assert_not_called()
