import threading
import time
from unittest.mock import Mock

import pytest


def test_blocked_telemetry_storage_keeps_receive_and_ui_clock_live(kivy_app, tmp_path, monkeypatch):
    from kivy.clock import Clock

    from carveracontroller.machine.telemetry_log import TelemetryLog
    from tests.integration.conftest import pump_frames

    controller = kivy_app.root.controller
    # This tests steady-state reception, not the scheduled metadata handshake.
    monkeypatch.setattr(kivy_app, "model", "C1")
    monkeypatch.setattr(kivy_app.root, "fw_version", "2.1.0c")
    monkeypatch.setattr(kivy_app.root, "config_loaded", True)
    entered, release = threading.Event(), threading.Event()
    writer = TelemetryLog(tmp_path / "blocked.jsonl", capacity=2)
    original = writer._write

    def blocked(record):
        entered.set()
        assert release.wait(10), "test failed to release storage"
        original(record)

    monkeypatch.setattr(writer, "_write", blocked)
    monkeypatch.setattr(controller, "_adaptive_log", writer)
    monkeypatch.setattr(controller, "stream", Mock())
    packet = "<Idle|MPos:-232,-195.285,-3|WPos:-232,-195.285,-53.480|S:0,12000,100,0,35|F:0,600,100>"
    finished = threading.Event()
    failures = []

    def receive():
        try:
            # Match streamIO's lock ownership, not only direct monitor calls.
            for _ in range(6):
                with controller._adaptive_lock:
                    controller.parseLine(packet)
        except Exception as error:
            failures.append(error)
        finally:
            finished.set()

    try:
        controller.parseLine(packet)
        assert entered.wait(2)
        threading.Thread(target=receive, daemon=True).start()
        assert finished.wait(2), "storage held the receive lock"
        assert not failures
        ticks = []
        Clock.schedule_once(lambda _dt: ticks.append(controller.machine_response_age(time.monotonic())), 0)
        pump_frames(2)
        assert ticks and ticks[0] is not None and ticks[0] < 2
        panel = kivy_app.root.desktop_workspace.telemetry_diagnostics
        state = controller.adaptive_monitor.snapshot(time.monotonic())
        state["persistence"] = controller.telemetry_persistence()
        panel.update(state, True)
        assert "2 pending" in panel.persistence.text and "5 lost" in panel.persistence.text
        controller.stream.send.assert_not_called()
    finally:
        release.set()
        receipt = writer.close(3)
    assert receipt["written"] == 2 and receipt["rejected"] == 5


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
    monkeypatch.setattr(root, "reconnection_popup", Mock(_is_open=True, desktop_visible=False))
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


def test_transfer_status_wait_does_not_disconnect_early_or_enable_jogging(kivy_app, monkeypatch):
    from carvera_sim.machine import SimulatedMachine

    from carveracontroller import main as module

    root, app = kivy_app.root, kivy_app
    controller = root.controller
    clock = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    for name, value in (
        ("stream", Mock()),
        ("_last_status_received_at", 80),
        ("_connection_started_at", 70),
        ("_refresh_heartbeat", False),
        ("_heartbeat_grace_until", 0),
        ("_connecting", False),
        ("_baud_switch_in_progress", False),
        ("sendNUM", 0),
        ("loadNUM", 0),
        ("paused", True),
        ("_status_reacquire_started_at", None),
        ("_status_reacquire_deadline", None),
        ("_status_poll_requested", False),
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
    monkeypatch.setattr(root, "heartbeat_time", module.time.time())
    monkeypatch.setattr(root, "reconnection_popup", Mock(_is_open=True, desktop_visible=False))
    monkeypatch.setattr(controller, "close", Mock())
    monkeypatch.setattr(root, "updateStatus", Mock())
    monkeypatch.setattr(app, "state", "Idle")
    monkeypatch.setattr(app, "playing", False)
    monkeypatch.setattr(app, "spindle_or_laser_is_on", False)
    controller.resumeStream()
    root.blink_state()
    controller.close.assert_not_called()
    assert not root._machine_allows_jogging()
    workspace = root.desktop_workspace
    workspace.refresh(0)
    assert workspace.state_label.text == "Awaiting status…"
    assert workspace.receive_age_metric.value.text == "20.00s"
    assert "5.0s remaining" in workspace.receive_age_metric.detail.text
    assert not workspace.hold_button.disabled
    clock[0] = 105
    root.blink_state()
    controller.close.assert_called_once_with()
    assert not root._machine_allows_jogging()
    controller.parseLine(SimulatedMachine().status_line())
    assert root._machine_allows_jogging()
    workspace.refresh(0)
    assert workspace.state_label.text == "Idle"
    assert workspace.receive_age_metric.value.text == "0.00s"
