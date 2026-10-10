"""Actual private-child status events drive monitoring and portable records."""

import json
import time
from collections import deque
from unittest.mock import Mock

import pytest

from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample
from carveracontroller.machine.desktop_control_owner import ControlBinding
from carveracontroller.machine.run_recording import RecordingReplay
from tests.integration import test_backend_job_file as job_support
from tests.integration import test_backend_job_run as run_support
from tests.integration import test_backend_live_report as support
from tests.integration.conftest import pump_frames

backend_scene = support.backend_scene
backend_connection = support.backend_connection
backend_job = job_support.backend_job
freeze_upload = job_support.freeze_upload
backend_run = run_support.backend_run


def wait_for(predicate, timeout=9, diagnostics=lambda: ""):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        pump_frames(3, sleep=0.03)
    assert predicate(), "Native backend condition did not become true: " + str(diagnostics())


@pytest.fixture
def telemetry_scene(backend_scene, monkeypatch):
    ws, viewer, panel, machine, methods, gui_send = backend_scene
    original_source = ws._backend_telemetry
    old_previous = ws.run_recording_panel.previous_buffer
    monkeypatch.setattr(ws, "_backend_telemetry", None)
    gui_monitor = AdaptiveMonitor()
    gui_monitor.observe(Sample(1, "Idle", 2000, 2000, None, 0, 100, (900, 900, 900)))
    monkeypatch.setattr(ws.machine.controller, "adaptive_monitor", gui_monitor)
    gui_command = Mock()
    monkeypatch.setattr(ws.machine.controller, "adaptiveCommand", gui_command)
    source = ws.backend_telemetry()
    machine.status = machine.status.replace(b"F:600,600,80", b"F:0,0,100")
    wait_for(lambda: source.monitor.last is not None and source.monitor.last.feed == 0)
    try:
        yield ws, source, panel, machine, gui_send, gui_command
    finally:
        ws.run_recording_panel.return_live()
        ws.run_recording_panel.previous_buffer = old_previous
        ws._backend_telemetry = original_source
        gui_send.assert_not_called()
        gui_command.assert_not_called()


def test_actual_event_receipts_capture_baseline_freeze_export_and_selected_diagnostics(
    telemetry_scene, tmp_path, monkeypatch
):
    ws, source, panel, _machine, gui_send, gui_command = telemetry_scene
    gui_buffer = ws.machine.controller.run_recording
    ws.select("Monitor")
    ws.monitor_section_buttons["Baseline"].dispatch("on_release")
    ws.refresh(0)
    capture = next(button for button, _guard in ws.guards if button.text == "Capture baseline")
    assert not capture.disabled and ws.can_capture_baseline()
    capture.dispatch("on_release")
    wait_for(
        lambda: source.monitor.baseline is not None,
        timeout=9,
        diagnostics=lambda: {
            "monitor": source.monitor.snapshot(time.monotonic()),
            "report": ws.backend_report().reason,
        },
    )
    assert source.monitor.baseline["rpm"] == 11950
    assert ws.machine.controller.adaptive_monitor.last.rpm == 2000
    assert not ws.machine.controller.adaptive_monitor.baseline
    ws.refresh(0)
    assert ws.monitor_rpm.value.text == "11,950" and "backend IPC" in ws.footer_status.text
    assert ws.run_recording is source.recording and ws.machine.controller.run_recording is gui_buffer
    record = ws.run_recording_panel
    ws.select("Job")
    ws.program_tasks.choose("Run record")
    record.freeze()
    wait_for(lambda: not record.busy and record.replay is not None)
    assert record.replay.payload["source"] == source.source and record.replay.payload["schema"] == 4
    record.step("last")
    assert "source receipt" in record.details.text and "firmware reference/units" in record.details.text
    archive = tmp_path / "actual-backend.cvrun"
    record._export_to(archive)
    wait_for(lambda: not record.busy and archive.exists())
    assert RecordingReplay(archive.read_bytes()).payload["source"] == source.source
    exported = tmp_path / "backend-diagnostics.json"
    monkeypatch.setattr(ws, "choose_profile_file", lambda selected, **kwargs: selected(exported))
    ws.telemetry_diagnostics.export()
    wait_for(lambda: not ws.telemetry_diagnostics._exporting and exported.exists())
    diagnostics = json.loads(exported.read_text())
    assert diagnostics["backend_source"]["connection_id"] == source.source["connection_id"]
    assert diagnostics["monitor"]["sample"]["rpm"] == 11950
    assert diagnostics["connection_receive"] is None and diagnostics["connection_generation"] is None
    assert diagnostics["monitor"]["active_control_available"] is False
    gui_send.assert_not_called()
    gui_command.assert_not_called()


def test_actual_ipc_queue_overflow_is_a_recorded_gap_and_invalidates_baseline(telemetry_scene, monkeypatch):
    ws, source, panel, _machine, _send, _command = telemetry_scene
    source.command("adaptive baseline")
    wait_for(lambda: source.monitor.baseline is not None, timeout=9)
    with panel.client._lock:
        receipts = panel.client._status_receipts
        monkeypatch.setattr(receipts, "items", deque(receipts.items, maxlen=2))
    refresh = ws._refresh_backend_telemetry
    monkeypatch.setattr(ws, "_refresh_backend_telemetry", lambda: None)
    cursor = source.cursor
    wait_for(lambda: panel.client.status_receipts(cursor)["lost_receipts"] >= 2)
    refresh()
    assert source.lost_receipts >= 2 and source.monitor.baseline is None and source.monitor.fault
    assert not source.monitor.capturing
    replay = RecordingReplay(source.recording.export_bytes())
    gaps = [event for event in replay.payload["events"] if event["kind"] == "source_gap"]
    assert gaps and sum(event["data"]["lost_receipts"] for event in gaps) == source.lost_receipts
    ws._refresh_monitor(False)
    assert ws.recording_alert.opacity == 1 and ws.monitor_feed.value.text == "—"


def test_replaced_backend_has_its_own_buffer_and_monitor_and_retains_previous_buffer(telemetry_scene, monkeypatch):
    ws, source, panel, _machine, _send, _command = telemetry_scene
    retained = source.recording.export_bytes()
    binding = ws.control_owner.binding
    monkeypatch.setattr(ws.control_owner, "binding", ControlBinding(binding.session_id, "replacement"))
    replacement = ws.backend_telemetry()
    assert replacement is not source and replacement.monitor.baseline is None
    assert replacement.recording.summary()["retained_events"] == 0
    assert ws.run_recording_panel.previous_buffer is source.recording
    ws.monitor_command("adaptive reset")
    ws._refresh_backend_telemetry()
    assert ws.run_recording is replacement.recording and not ws.can_capture_baseline()
    assert source.recording.export_bytes() == retained
    assert panel.client.session_id == binding.session_id


def test_returning_to_gui_owner_retires_backend_capture_and_never_reuses_baseline(telemetry_scene, monkeypatch):
    ws, source, _panel, _machine, _send, _command = telemetry_scene
    binding = ws.control_owner.binding
    gui_buffer = ws.machine.controller.run_recording
    stop = Mock()
    monkeypatch.setattr(ws.run_recording_panel, "shutdown_camera", stop)
    monkeypatch.setattr(ws.control_owner, "binding", None)
    assert ws.run_recording is gui_buffer and ws._backend_telemetry is None
    assert ws.run_recording_panel.previous_buffer is source.recording
    stop.assert_called_once_with()
    assert ws.run_recording is gui_buffer
    stop.assert_called_once_with()
    monkeypatch.setattr(ws.control_owner, "binding", binding)
    assert ws.backend_telemetry() is not source and ws.run_recording.source == source.source
    assert ws.run_recording.summary()["retained_events"] == 0


def test_prepared_recording_cannot_activate_after_backend_owner_replacement(telemetry_scene, tmp_path, monkeypatch):
    ws, source, _panel, _machine, _send, _command = telemetry_scene
    record = ws.run_recording_panel
    filename = tmp_path / "declared-program.nc"
    filename.write_text("G21\nG90\nM2\n")
    monkeypatch.setattr(ws.app, "selected_local_filename", str(filename))
    work = []
    monkeypatch.setattr(record, "_worker", lambda action, done: work.append((action, done)))
    record.start_recording()
    assert len(work) == 1
    prepared = work[0][0]()
    assert prepared[0].source == source.source
    binding = ws.control_owner.binding
    monkeypatch.setattr(ws.control_owner, "binding", ControlBinding(binding.session_id, "replacement"))
    new_buffer = ws.run_recording
    work[0][1](prepared)
    assert ws.run_recording is new_buffer and "not activated" in record.notice.text


def test_repeated_workbench_refresh_does_not_duplicate_private_receipt(telemetry_scene):
    ws, source, panel, _machine, _send, _command = telemetry_scene
    with panel.client._lock:
        before = source.recording.summary()["retained_events"]
        cursor = source.cursor
        latest = panel.client.status_receipts(cursor)["latest_sequence"]
        ws._refresh_backend_telemetry()
        once = source.recording.summary()["retained_events"]
        for _ in range(10):
            ws._refresh_backend_telemetry()
        assert source.cursor == latest and source.recording.summary()["retained_events"] == once
        assert once >= before
    pump_frames(2)


def test_transfer_completion_has_independent_current_lease_receipt_before_next_step(backend_job):
    panel, backend, _ws, _state, requests, _setup = backend_job
    freeze_upload(panel)
    upload = panel.job.receipts[-1]
    assert upload["post_transfer_state"]["outcome"] == "current_connection_idle_transfer"
    assert backend.client.snapshot()["last_machine_snapshot"]["transfer_active"] is False
    panel.verify_action.dispatch("on_release")
    wait_for(lambda: not panel.busy)
    assert (
        panel.job.phase == "verified"
        and panel.job.receipts[-1]["post_transfer_state"]["outcome"] == "current_connection_idle_transfer"
    )
    assert [method for method, _params in requests].count("upload") == 1
    assert [method for method, _params in requests].count("download") == 1


def test_background_cache_poll_does_not_lock_foreground_actions(telemetry_scene, monkeypatch):
    from concurrent.futures import Future

    _ws, _source, panel, _machine, _send, _command = telemetry_scene
    pending = Future()
    submit = Mock(return_value=pending)
    monkeypatch.setattr(panel.client, "submit", submit)
    panel.polling = False
    panel.busy = False
    note = panel.note.text
    panel.request("snapshot", background=True)
    assert panel.polling and not panel.busy and panel.note.text == note
    panel.request("snapshot", background=True)
    submit.assert_called_once_with("snapshot")


def test_run_intent_refreshes_private_cache_before_final_ui_admission(backend_run):
    _panel, _backend, _ws, _state, requests, _setup = backend_run
    run = run_support.prepare_run(backend_run)
    start = len(requests)
    run_support.start_review(run)
    run_support.wait_phase(run, "playing_reported")
    submitted = requests[start:]
    operation = next(i for i, (method, _params) in enumerate(submitted) if method == "operation")
    assert operation > 0 and all(method == "snapshot" for method, _params in submitted[:operation])
    assert sum(method == "operation" for method, _params in submitted) == 1
