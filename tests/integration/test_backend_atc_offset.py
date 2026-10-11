import json
import socket

import pytest
from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_atc_offset import export_offset, read_offset
from carveracontroller.desktop_components import Action
from carveracontroller.desktop_tool_observation import observe_tool
from carveracontroller.machine.backend_live_report import backend_live_report
from carveracontroller.machine.probe_settings_workflow import load_journal
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job  # noqa: F401
from tests.integration.test_backend_tool_measurement import measurement_workbench  # noqa: F401
from tests.unit.test_atc_offset import LINE


@pytest.fixture
def offset_workbench(measurement_workbench):  # noqa: F811
    panel, backend, ws, state, requests = measurement_workbench
    state.status = state.status.replace(b"MPos:1,2,3|", b"MPos:1,2,3,0|").replace(b"|G:0", b"|R:0|G:0")
    prior = state.command_handler
    state.offset_queries, state.offset_mode = [], "complete"

    def handler(sock, command):
        if command == b"M499\n":
            state.offset_queries.append(command)
            if state.offset_mode == "drop":
                sock.shutdown(socket.SHUT_RDWR)
            elif state.offset_mode == "duplicate":
                sock.sendall(LINE[:-3] + LINE)
            elif state.offset_mode == "wrong_tool":
                sock.sendall(LINE.replace(b"tool:1", b"tool:2"))
            else:
                sock.sendall(LINE)
            return True
        return prior(sock, command)

    state.command_handler = handler
    ws.backend_report = lambda: backend_live_report(
        ws.control_owner,
        backend.client.session_id,
        backend.client.snapshot(),
        ws.selected_machine_profile,
        __import__("time").monotonic(),
    )
    wait_for(lambda: ws.backend_report().pose is not None)
    panel.read_identity()
    wait_for(lambda: not panel.busy)
    assert panel.identity is not None
    yield panel, backend, ws, state, requests


def test_actual_child_original_m499_receipt_export_and_historical_expiry_are_command_free_after_read(
    offset_workbench, tmp_path
):
    panel, backend, ws, state, requests = offset_workbench
    prior = panel.latest_record
    events = list(ws.machine.tool_custody.events)
    panel.atc_offset_action.dispatch("on_release")
    wait_for(lambda: not panel.busy)
    assert panel.atc_offset_record["phase"] == "atc_offset_report_retained", panel.note.text
    assert panel.atc_offset_observation is not None
    panel.refresh()
    assert "Fresh read" in panel.atc_offset_summary.text
    assert panel.latest_record is prior
    assert state.offset_queries == [b"M499\n"] and state.measurements == []
    value = panel.atc_offset_record["qualified_report"]
    assert value["atc_offset_mm"] == -21.491 and value["applied_robot_offset_verified"] is False
    assert value["ipc"]["original_ipc_bytes_base64"]
    assert load_journal(panel.atc_offset_path)[-1]["record"]["qualified_report"] == value
    observation = observe_tool(ws, __import__("time").monotonic())
    assert observation.current, observation.reason
    assert observation.pose is not None, observation.reason
    assert observation.pose.tool_length_mm is None and observation.raw_offset == 12
    assert observation.atc_offset is not None
    assert observation.atc_offset.receipt["atc_offset_mm"] == -21.491
    callback = []
    ws.choose_profile_file = lambda selected, **kwargs: callback.append(selected)
    export_offset(panel)
    target = tmp_path / "offset.json"
    callback.pop()(str(target))
    wait_for(lambda: not panel.busy)
    assert json.loads(target.read_text()) == panel.atc_offset_record
    pump_frames(22, sleep=0.05)
    panel.refresh()
    assert "historical" in panel.atc_offset_summary.text
    assert observe_tool(ws, __import__("time").monotonic()).atc_offset is None
    assert state.offset_queries == [b"M499\n"] and ws.machine.tool_custody.events == events
    for width in (360, 760):
        panel.width = dp(width)
        pump_frames(8)
        for widget in panel.walk():
            if isinstance(widget, Action):
                assert widget.texture_size[0] <= widget.width, widget.text
        filename = tmp_path / f"atc-offset-{width}.png"
        panel.export_to_png(str(filename))
        assert filename.exists()


@pytest.mark.parametrize("mode", ["duplicate", "wrong_tool", "drop"])
def test_failed_original_query_remains_retained_without_retry_or_offset_promotion(offset_workbench, mode):
    panel, backend, ws, state, _requests = offset_workbench
    state.offset_mode = mode
    read_offset(panel)
    wait_for(lambda: not panel.busy)
    assert panel.atc_offset_record["phase"] == "atc_offset_read_unresolved"
    assert panel.atc_offset_observation is None
    assert "qualified_report" not in panel.atc_offset_record
    assert state.offset_queries == [b"M499\n"] and state.measurements == []
    assert load_journal(panel.atc_offset_path)[-1]["record"] == panel.atc_offset_record
    pump_frames(4)
    assert state.offset_queries == [b"M499\n"]


@pytest.mark.parametrize("change", ["intent_failure", "context", "owner"])
def test_durable_intent_and_same_callback_context_guard_precede_actual_query(offset_workbench, monkeypatch, change):
    import carveracontroller.desktop_atc_offset as module

    panel, backend, ws, state, _requests = offset_workbench
    original = module.append_journal

    def append(path, record, **kwargs):
        if record["phase"] == "atc_offset_read_pending":
            if change == "intent_failure":
                raise OSError("Intent unavailable")
            original(path, record, **kwargs)
            if change == "context":
                ws.loaded_toolset = {"id": "replaced"}
            else:
                ws.control_owner.binding = None
        else:
            original(path, record, **kwargs)

    monkeypatch.setattr(module, "append_journal", append)
    read_offset(panel)
    wait_for(lambda: not panel.busy)
    assert panel.atc_offset_record["phase"] == "atc_offset_not_submitted"
    assert panel.atc_offset_record["submitted"] is False
    assert state.offset_queries == [] and state.measurements == []
    assert panel.atc_offset_observation is None


@pytest.mark.parametrize("change", ["owner", "profile"])
def test_retired_result_keeps_original_receipt_and_cannot_become_current(offset_workbench, change):
    panel, backend, ws, state, requests = offset_workbench
    handler = state.command_handler

    def retire(sock, command):
        if command == b"M499\n":
            if change == "owner":
                ws.control_owner.binding = None
            else:
                ws.selected_machine_profile = dict(ws.selected_machine_profile, name="Replacement")
        return handler(sock, command)

    state.command_handler = retire
    read_offset(panel)
    wait_for(lambda: not panel.busy)
    assert panel.atc_offset_record["phase"] == "atc_offset_report_retained"
    assert panel.atc_offset_observation is None
    assert "historical" in panel.note.text
    assert panel.atc_offset_record["qualified_report"]["atc_offset_mm"] == -21.491
    assert state.offset_queries == [b"M499\n"] and state.measurements == []


def test_pending_measurement_refuses_offset_query_without_altering_calibration_attempt(offset_workbench):
    panel, backend, ws, state, requests = offset_workbench
    original = panel.latest_record
    binding = ws.control_owner.binding
    panel.operation_binding = (binding.session_id, binding.connection_id)
    read_offset(panel)
    assert state.offset_queries == [] and panel.atc_offset_record is None
    assert panel.latest_record is original
    assert "pending or unresolved" in panel.note.text
