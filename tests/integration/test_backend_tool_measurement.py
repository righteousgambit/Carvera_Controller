import copy
import socket
import threading
from types import SimpleNamespace

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.desktop_backend_transactions import require_idle_transaction
from carveracontroller.desktop_components import Action
from carveracontroller.desktop_tool_measurement import ToolMeasurementPanel
from carveracontroller.machine.probe_settings_workflow import append_journal, load_journal
from carveracontroller.machine.tool_custody import ToolCustodyStore
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job  # noqa: F401
from tests.unit.test_tool_measurement import REPORT


@pytest.fixture
def measurement_workbench(backend_job, tmp_path):  # noqa: F811
    job, backend, ws, state, requests, _setup = backend_job
    ws.selected_machine_profile.update({"name": "Loopback Carvera", "model": "C1"})
    ws.machine.gcode_viewer = SimpleNamespace(
        library_tool_table_mm={1: ToolDefinition(1, diameter=6.35, description="Quarter-inch cutter")}
    )
    ws.machine.tool_custody = ToolCustodyStore(tmp_path / "custody.json")
    ws.loaded_toolset = {"id": "first-bank"}
    ws.tool_comparison = SimpleNamespace(custody=SimpleNamespace(selected_id=None))
    state.status = b"<Idle|MPos:1,2,3|WPos:4,5,6|C:1,4,0,1|S:0,0,100|T:1,12|G:0|P:0,0,0,0>\n"
    state.mode, state.measurements, state.output_timers = "window", [], []

    def handler(sock, command):
        if command == b"model\n":
            sock.sendall(b"model = C1, 1, 4, 1\n")
        elif command == b"version\n":
            sock.sendall(b"version = 2.1.0c\n")
        elif command.startswith(b"M491 R"):
            state.measurements.append(command)
            if state.mode == "reject":
                sock.sendall(b"ERROR: calibration refused\nok\n")
            elif state.mode == "drop":
                # Intentional disconnect ends this fixture server immediately.
                state.stop.set()
                sock.shutdown(socket.SHUT_RDWR)
            elif state.mode == "window":
                sock.sendall(REPORT.encode() + b"ok\n")
            elif state.mode == "ack_only":
                sock.sendall(b"ok\n")
            else:
                state.status = state.status.replace(b"<Idle", b"<Run").replace(b"P:0,0,0,0", b"P:0,0,0,1")
                sock.sendall(b"ok\n")

                def late():
                    if not state.stop.is_set():
                        sock.sendall(
                            b"ERROR: setter output failed\n" if state.mode == "late_failure" else REPORT.encode()
                        )
                        state.status = state.status.replace(b"<Run", b"<Idle").replace(b"P:0,0,0,1", b"P:0,0,0,0")

                timer = threading.Timer(0.2, late)
                state.output_timers.append(timer)
                timer.start()
        else:
            return False
        return True

    state.command_handler = handler
    panel = ToolMeasurementPanel(ws, storage_root=tmp_path / "measurements", size_hint=(None, None), width=dp(650))
    ws.tool_measurement_panel = panel
    Window.add_widget(panel)
    timer = Clock.schedule_interval(lambda _dt: panel.refresh(), 0.1)
    panel.target.text = next(v for v in panel.target.values if v.startswith("T1 ·"))
    panel.kind.text = "Installed cutter"
    try:
        pump_frames(20, sleep=0.04)
        backend.request("snapshot")
        wait_for(lambda: not backend.busy)
        yield panel, backend, ws, state, requests
    finally:
        timer.cancel()
        panel.dispose()
        for worker in state.output_timers:
            worker.join(5)
        # Retire this new fixture's loopback peer before its owning SDK closes.
        # Existing fixture assertions/deadlines are unchanged.
        state.stop.set()
        pump_frames(2, sleep=0.06)
        Window.remove_widget(panel)


def prepared(panel):
    panel.read_identity()
    wait_for(lambda: not panel.busy)
    assert panel.identity is not None, panel.note.text
    panel.review_measurement()
    wait_for(lambda: not panel.busy)
    assert panel.review is not None, panel.note.text
    return panel.review


@pytest.mark.parametrize("mode", ["window", "late"])
def test_actual_child_ack_output_idle_and_unassigned_import_have_distinct_receipts(
    measurement_workbench, tmp_path, mode
):
    panel, backend, ws, state, requests = measurement_workbench
    state.mode = mode
    ticket = prepared(panel)
    ticks = []
    heartbeat = Clock.schedule_interval(lambda _dt: ticks.append(1), 0.01)
    try:
        panel.measurement_action.dispatch("on_release")
        wait_for(lambda: not panel.busy and panel.latest_record["phase"] == "later_idle_reported")
        assert state.measurements == [b"M491 R3\n"] and ticks
        assert panel.operation_binding is None
        record = load_journal(panel.journal_path)[-1]["record"]
        assert record["motion_completed"] is False and record["physical_tool_identity_verified"] is False
        assert record["response"]["original_ipc_bytes_base64"]
        if mode == "late":
            assert record["acknowledgement"]["calibration"] is None
            assert record["normalized_output_is_qualified_calibration"] is False
            assert record["received_output"] and all(r["original_ipc_bytes_base64"] for r in record["received_output"])
            assert record["normalized_projection"]["printed_using_is_applied_tlo"] is False
            panel.refresh()
            assert panel.capture_action.disabled
            panel.capture_samples()
            assert ws.machine.tool_custody.events == []
        else:
            assert record["acknowledgement"]["calibration"]["report"]["applied"] is None
            panel.capture_samples()
            wait_for(lambda: not panel.busy)
            assert panel.latest_record["phase"] == "samples_imported_unassigned", panel.note.text
            event = ws.machine.tool_custody.events[0]
            assert event["tool_number"] is None and event["report"]["applied"] is None
            assert event["endpoint"] == f"{backend.client.host}:{backend.client.port}"
            assert event["source_evidence"]["response"]["original_ipc_bytes_base64"]
            assert event["source_evidence"]["command_attribution_verified"] is False
            panel.capture_samples()
            pump_frames(2)
            assert len(ws.machine.tool_custody.events) == 1
        before = copy.deepcopy([r for r in requests if r[0] != "snapshot"])
        panel.inspect_attempts()
        wait_for(lambda: not panel.busy)
        assert [r for r in requests if r[0] != "snapshot"] == before
        assert state.measurements == [b"M491 R3\n"]
        for width in (360, 760):
            panel.width = dp(width)
            pump_frames(10)
            for widget in panel.walk(restrict=True):
                if isinstance(widget, Action):
                    assert widget.texture_size[0] <= widget.width, (width, widget.text, widget.width)
            panel.export_to_png(str(tmp_path / f"measurement-{mode}-{width}.png"))
        ws.machine.controller.executeCommand.assert_not_called()
    finally:
        heartbeat.cancel()


@pytest.mark.parametrize("change", ["repeat", "kind", "owner", "intent_failure"])
def test_final_ui_callback_rechecks_context_after_durable_intent(measurement_workbench, monkeypatch, change):
    panel, backend, ws, state, requests = measurement_workbench
    ticket = prepared(panel)
    import carveracontroller.desktop_tool_measurement as implementation

    def intercept(path, record, **kwargs):
        if record["phase"] == "measurement_pending":
            if change == "intent_failure":
                raise OSError("Synthetic unavailable intent storage")
            append_journal(path, record, **kwargs)

            def changed(_dt):
                if change == "repeat":
                    panel.repeats.text = "4"
                elif change == "kind":
                    panel.kind.text = "Installed probe"
                else:
                    ws.control_owner.binding = None

            Clock.schedule_once(changed, 0)
        else:
            append_journal(path, record, **kwargs)

    monkeypatch.setattr(implementation, "append_journal", intercept)
    panel.measurement(ticket)
    wait_for(lambda: not panel.busy)
    assert state.measurements == []
    assert not any(method == "operation" and params.get("operation") == "tool.measure" for method, params in requests)
    assert panel.latest_record["submitted"] is False
    assert panel.latest_record["phase"] == "not_submitted"
    assert panel.operation_binding is None


def test_ack_without_samples_or_activity_stays_unresolved_and_blocks_other_workflows(measurement_workbench):
    panel, backend, ws, state, requests = measurement_workbench
    state.mode = "ack_only"
    ticket = prepared(panel)
    panel.measurement(ticket)
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "measurement_acknowledged"
    assert panel.operation_binding == (ticket.session_id, ticket.connection_id)
    for requester in ("job", "probe", "exchange"):
        with pytest.raises(ValueError, match="measurement"):
            require_idle_transaction(ws, requester)
    pump_frames(15, sleep=0.04)
    assert panel.operation_binding is not None and state.measurements == [b"M491 R3\n"]
    assert ws.machine.tool_custody.events == []


@pytest.mark.parametrize("mode", ["reject", "drop"])
def test_controller_failure_stays_unresolved_without_replay_or_import(measurement_workbench, mode):
    panel, backend, ws, state, requests = measurement_workbench
    state.mode = mode
    ticket = prepared(panel)
    panel.measurement(ticket)
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "measurement_unresolved"
    assert panel.latest_record["submitted"] is True
    assert panel.operation_binding == (ticket.session_id, ticket.connection_id)
    assert ws.machine.tool_custody.events == []
    panel.inspect_attempts()
    wait_for(lambda: not panel.busy)
    assert state.measurements == [b"M491 R3\n"]


def test_owner_retirement_leaves_original_attempt_historical(measurement_workbench):
    panel, backend, ws, state, requests = measurement_workbench
    state.mode = "ack_only"
    ticket = prepared(panel)
    panel.measurement(ticket)
    wait_for(lambda: not panel.busy)
    path, original = panel.journal_path, panel.journal_path.read_bytes()
    ws.control_owner.binding = None
    panel.refresh()
    assert panel.observation_review is None
    assert path.read_bytes() == original
    assert "historical" in panel.note.text
    assert ws.machine.tool_custody.events == []


def test_late_failure_is_retained_after_ack_without_qualifying_samples(measurement_workbench):
    panel, backend, ws, state, requests = measurement_workbench
    state.mode = "late_failure"
    ticket = prepared(panel)
    panel.measurement(ticket)
    wait_for(lambda: not panel.busy and panel.latest_record["phase"] == "measurement_output_unresolved")
    record = load_journal(panel.journal_path)[-1]["record"]
    assert record["received_output"][0]["text"] == "ERROR: setter output failed"
    assert record["received_output"][0]["original_ipc_bytes_base64"]
    assert record["submitted"] is True and panel.operation_binding is not None
    assert ws.machine.tool_custody.events == []
