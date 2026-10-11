"""Actual native startup inspection is passive and retains failed attempts."""

import json
import sys
from types import SimpleNamespace

from kivy.core.window import Window

from carveracontroller.desktop_backend import BackendPanel
from carveracontroller.headless.client import SupervisorClient
from tests.integration import test_backend_connection as support
from tests.integration.conftest import pump_frames, set_window_viewport

backend_connection = support.backend_connection
wait_for = support.wait_for


def test_actual_child_inspection_copy_and_stopped_receipt_do_not_poll_or_connect(backend_connection, monkeypatch):
    panel, _ws, machine, methods = backend_connection
    copies = []
    monkeypatch.setattr("carveracontroller.desktop_backend_startup.Clipboard.copy", copies.append)
    panel.startup_action.dispatch("on_release")
    pump_frames(4)
    popup = panel.startup_popup
    assert popup.startup_record["startup"]["phase"] == "ready"
    assert "Process launch:" in popup.startup_timing.text
    assert "Startup: ready" in popup.startup_summary.text
    assert popup.startup_record["startup"]["ready_event_sha256"]
    popup.copy_action.dispatch("on_release")
    assert json.loads(copies[-1]) == popup.startup_record
    assert methods == ["snapshot"] and not machine.accepted.is_set()
    popup.dismiss()
    panel.stop_action.dispatch("on_release")
    wait_for(lambda: panel.client is None and not panel.busy)
    assert not panel.startup_action.disabled
    panel.startup_action.dispatch("on_release")
    retained = panel.startup_popup.startup_record
    assert retained["startup"]["phase"] == "ready"
    assert retained["startup"]["process_returncode"] == 0
    assert retained["running_at_observation"] is False and retained["ready_at_observation"] is False
    assert methods == ["snapshot"] and not machine.accepted.is_set()


def test_failed_actual_child_is_inspectable_after_it_is_reaped_without_a_retry():
    clients = []

    def factory(host, port):
        client = SupervisorClient(host, port, argv=[sys.executable, "-u", "-c", "print('malformed',flush=True)"])
        clients.append(client)
        return client

    ws = SimpleNamespace(selected_machine_profile={"id": "failed-local", "host": "127.0.0.1", "port": 2222})
    panel = BackendPanel(ws, client_factory=factory)
    Window.add_widget(panel)
    try:
        panel.start()
        wait_for(lambda: not panel.busy)
        assert panel.client is None and len(clients) == 1
        assert not panel.startup_action.disabled
        assert "Inspect startup timing" in panel.note.text
        panel.startup_action.dispatch("on_release")
        retained = panel.startup_popup.startup_record
        assert retained["startup"]["failure_code"] == "readiness_protocol_failed"
        assert retained["startup"]["process_returncode"] == 0
        assert retained["profile_id_at_start"] == "failed-local"
        assert clients[0].snapshot()["pending_requests"] == 0
        assert clients[0].snapshot()["last_machine_snapshot"] is None
        assert len(clients) == 1
    finally:
        panel.dispose()
        for client in clients:
            client.close()
        Window.remove_widget(panel)


def test_startup_inspector_scrolls_at_short_height_and_disposes_its_popup(tmp_path):
    previous = Window.size
    ws = SimpleNamespace(selected_machine_profile=None)
    panel = BackendPanel(ws)
    Window.add_widget(panel)
    try:
        set_window_viewport(700, 360)
        panel.startup_record = {
            "session_id": "synthetic-layout-example",
            "pid": 123,
            "host": "127.0.0.1",
            "port": 2222,
            "running_at_observation": False,
            "ready_at_observation": False,
            "startup": {
                "phase": "timed_out",
                "configured_ready_wait_limit_s": 5,
                "failure_code": "readiness_wait_timed_out",
                "stderr_bytes_drained": 0,
            },
        }
        panel.inspect_startup()
        pump_frames(8)
        popup = panel.startup_popup
        assert popup.height <= Window.height * 0.9 + 1
        assert popup.content._viewport.height > popup.content.height
        assert "Unknown" in popup.startup_timing.text
        popup.export_to_png(str(tmp_path / "startup-inspector-short.png"))
        panel.dispose()
        wait_for(lambda: not popup._is_open)
    finally:
        panel.dispose()
        Window.remove_widget(panel)
        Window.size = previous
        pump_frames(4)
