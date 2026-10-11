import threading
from unittest.mock import Mock

import pytest

from carveracontroller.machine.desktop_control_owner import DesktopControlOwner
from tests.integration import test_backend_connection as backend_support
from tests.integration.conftest import pump_frames

backend_connection = backend_support.backend_connection
wait_for = backend_support.wait_for


def test_main_workbench_handoff_routes_stop_actions_to_real_child_and_refuses_gui_fallback(
    backend_connection, kivy_app, monkeypatch, tmp_path
):
    panel, original_workspace, machine, methods = backend_connection
    ws = kivy_app.root.desktop_workspace
    controller = ws.machine.controller
    monkeypatch.setattr(ws, "backend_panel", panel)
    monkeypatch.setattr(ws, "control_owner", DesktopControlOwner())
    monkeypatch.setattr(ws, "selected_machine_profile", original_workspace.selected_machine_profile)
    monkeypatch.setattr(controller, "stream", None)
    monkeypatch.setattr(ws, "_connection_opening", lambda: False)
    panel.workspace = ws
    try:
        ws.select("Settings")
        ws.machine_tasks.show("Backend")
        panel.connect_action.dispatch("on_release")
        wait_for(lambda: not panel.busy and "actual 11950 RPM" in panel.telemetry.text)
        assert not ws.control_owner.backend_selected
        opening, finish_open = threading.Event(), threading.Event()

        def slow_gui_open(*_args):
            opening.set()
            assert finish_open.wait(4)
            return False

        with monkeypatch.context() as scoped:
            scoped.setattr(controller, "_open_owned", slow_gui_open)
            worker = threading.Thread(target=lambda: controller.open(1, "127.0.0.1"))
            worker.start()
            try:
                assert opening.wait(2)
                assert not ws.claim_backend_controls() and not ws.control_owner.backend_selected
                assert "opening or writing" in panel.ownership_note.text
                # Exercise the periodic UI callback while open retains command ownership.
                ws.refresh(0)
                pump_frames(3)
                assert worker.is_alive()
            finally:
                finish_open.set()
                worker.join(4)
                assert not worker.is_alive()
        panel.claim_action.dispatch("on_release")
        assert ws.control_owner.backend_selected and ws._backend_control_available()
        identity = ws.control_owner.binding
        ws.select("Job")
        ws.refresh(0)
        assert ws.state_label.text == "Idle" and "Backend owner" in ws.connection_label.text
        assert ws.hold_button.text == "Feed hold" and not ws.hold_button.disabled and not ws.stop_button.disabled
        assert ws.program_action_buttons["Review & start"].disabled and not ws._can_connect_profile()
        assert not ws.connected and ws.machine.gcode_viewer.observed_pose is None
        assert ws.rpm_metric.value.text == "—" and ws.tool_metric.value.text == "—"
        machine.status = b"<Hold|MPos:1,2,3,45|WPos:4,5,6,45|C:0,4,0,1|S:11950,12000,100|F:600,0,80|T:2>\n"
        wait_for(lambda: not panel.busy and ws.hold_button.text == "Resume motion" and not ws.hold_button.disabled)
        ws.hold_button.dispatch("on_release")
        ws.hold_button.dispatch("on_release")
        wait_for(lambda: machine.resumed.is_set() and len(panel.control_receipts) == 1)
        assert machine.wire.count(b"~") == 1 and methods.count("realtime") == 1
        assert panel.control_receipts[-1]["action"] == "cycle_resume"
        assert "Motion completion is unconfirmed" in panel.control_note.text
        machine.status = b"<Idle|MPos:1,2,3,45|WPos:4,5,6,45|C:0,4,0,1>\n"
        wait_for(lambda: not panel.busy and ws.hold_button.text == "Feed hold")
        gui_stream = Mock()
        monkeypatch.setattr(controller, "stream", gui_stream)
        assert controller.executeCommand("M821") is False
        controller.executeRealtime(ord("~"))
        controller.executeFileCommand("upload /sd/gcodes/unreviewed.nc")
        gui_stream.send.assert_not_called()
        ws.hold_button.dispatch("on_release")
        ws.stop_button.dispatch("on_release")
        wait_for(lambda: machine.held.is_set() and machine.aborted.is_set() and len(panel.control_receipts) == 3)
        gui_stream.send.assert_not_called()
        assert all(row["connection_id"] == identity.connection_id for row in panel.control_receipts)
        assert not ws.release_backend_controls() and ws.control_owner.binding == identity
        generation = controller._connection_generation
        assert controller.open(1, "192.168.0.79") is False
        assert controller._connection_generation == generation and controller.stream is gui_stream
        gui_stream.close.assert_not_called()
        ws._connection_menu()
        assert ws.active_section == "Settings" and ws.machine_tasks.active == "Backend"
        pump_frames(5)
        ws.machine_controls.export_to_png(str(tmp_path / "backend-owned-header.png"))
        panel.client.close()
        ws.refresh(0)
        assert ws.control_owner.binding == identity and not ws._backend_control_available()
        assert ws.hold_button.disabled and ws.stop_button.disabled
        assert ws.state_label.text == "Backend status unavailable"
        before = len(methods)
        ws._feed_hold()
        ws._stop_machine()
        ws._review_start()
        assert len(methods) == before
        assert controller.executeCommand("M821") is False
        gui_stream.send.assert_not_called()
        panel.release_action.dispatch("on_release")
        assert not ws.control_owner.backend_selected
        # The real GUI watchdog may close the intentionally report-less GUI
        # stream. Returning ownership opens nothing; declare a fresh synthetic
        # GUI transport before checking its ordinary send path.
        replacement_stream = Mock()
        monkeypatch.setattr(controller, "stream", replacement_stream)
        assert controller.executeCommand("M821") is True
        replacement_stream.send.assert_called_once()
    finally:
        panel.workspace = original_workspace
        ws.control_owner.binding = None


@pytest.mark.parametrize("route", ["command", "realtime", "file"])
def test_actual_gui_send_boundary_preserves_prior_guard_and_refuses_backend_selected_writer(
    kivy_app, monkeypatch, route
):
    ws = kivy_app.root.desktop_workspace
    controller = ws.machine.controller
    stream = Mock()
    monkeypatch.setattr(controller, "stream", stream)
    prior = Mock(return_value=False)
    monkeypatch.setattr(ws, "_prior_command_owner_guard", prior)
    before = controller.receive_diagnostics()["current"]["control_writes"]["total_calls"]
    if route == "command":
        assert controller.executeCommand("M821") is False
    elif route == "realtime":
        controller.executeRealtime(ord("!"))
    else:
        controller.executeFileCommand("upload /sd/gcodes/test.nc")
    prior.assert_called_once()
    stream.send.assert_not_called()
    assert controller.receive_diagnostics()["current"]["control_writes"]["total_calls"] == before


@pytest.mark.parametrize(
    "change", ["stale", "missing_age", "unknown", "transfer", "busy", "connection", "session", "run"]
)
def test_backend_resume_revalidates_current_bound_hold_report_without_gui_or_backend_fallback(change):
    from types import SimpleNamespace

    from carveracontroller.desktop_backend import BackendPanel

    state = {
        "ready": True,
        "running": True,
        "last_machine_snapshot_age_s": 0.1,
        "last_machine_snapshot": {
            "connected": True,
            "connection_id": "one",
            "status_age_ms": 100,
            "status": {"state": "Hold"},
            "unknown_outcome": False,
            "transfer_active": False,
        },
    }
    owner = DesktopControlOwner()
    owner.claim("child", state, gui_busy=False)
    client = SimpleNamespace(session_id="child", snapshot=lambda: state, submit=Mock(), close=Mock())
    panel = BackendPanel(SimpleNamespace(control_owner=owner))
    panel.client = client
    assert panel.can_resume()
    if change == "stale":
        state["last_machine_snapshot_age_s"] = 1
    elif change == "missing_age":
        state.pop("last_machine_snapshot_age_s")
    elif change == "unknown":
        state["last_machine_snapshot"]["unknown_outcome"] = True
    elif change == "transfer":
        state["last_machine_snapshot"]["transfer_active"] = True
    elif change == "busy":
        panel.busy = True
    elif change == "connection":
        state["last_machine_snapshot"]["connection_id"] = "replacement"
    elif change == "session":
        client.session_id = "replacement"
    elif change == "run":
        state["last_machine_snapshot"]["status"]["state"] = "Run"
    panel.request_resume()
    assert not panel.can_resume() and "Resume withheld" in panel.control_note.text
    assert owner.backend_selected and not panel.control_pending
    client.submit.assert_not_called()
    panel.dispose()


@pytest.mark.parametrize("prior_allows", [True, False])
def test_retiring_workspace_keeps_prior_guard_and_waits_for_its_owned_child_to_stop(
    kivy_app, monkeypatch, prior_allows
):
    from types import SimpleNamespace

    ws = kivy_app.root.desktop_workspace
    owner = DesktopControlOwner()
    state = {"ready": True, "running": True, "last_machine_snapshot": {"connected": True, "connection_id": "one"}}
    owner.claim("child", state, gui_busy=False)
    monkeypatch.setattr(ws, "control_owner", owner)
    monkeypatch.setattr(ws, "backend_panel", SimpleNamespace(client=SimpleNamespace(snapshot=lambda: state)))
    prior = Mock(return_value=prior_allows)
    monkeypatch.setattr(ws, "_prior_command_owner_guard", prior)
    assert not ws.machine.controller.command_owner_available()
    monkeypatch.setattr(ws, "_control_owner_closed", True)
    assert not ws.machine.controller.command_owner_available()
    prior.assert_not_called()
    state["running"] = False
    assert ws.machine.controller.command_owner_available() is prior_allows
    prior.assert_called_once()
    assert owner.backend_selected  # Retirement does not manufacture a live handoff.
