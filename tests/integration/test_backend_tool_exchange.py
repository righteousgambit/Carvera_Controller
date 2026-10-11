import hashlib
import socket
from types import SimpleNamespace

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_tool_exchange import ToolExchangePanel
from carveracontroller.machine.probe_settings_workflow import load_journal
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job  # noqa: F401 - pytest fixture


@pytest.fixture
def exchange_workbench(backend_job, tmp_path):  # noqa: F811 - imported pytest fixture
    _job, backend, ws, state, requests, _setup = backend_job
    ws.selected_machine_profile.update({"name": "Loopback Carvera", "model": "C1"})
    ws.loaded_toolset = {"id": "aluminum", "name": "Aluminum bank"}
    ws.machine.gcode_viewer = SimpleNamespace(
        library_tool_table_mm={
            1: ToolDefinition(1, ToolType.FLAT_END_MILL, 6.35, description="Quarter rougher"),
            2: ToolDefinition(2, ToolType.BALL_END_MILL, 3.175, description="Ball finish"),
            8: ToolDefinition(8, ToolType.DRILL, 3, description="Second bank drill"),
        }
    )
    state.status = b"<Idle|MPos:1,2,3|WPos:4,5,6|C:1,4,0,1|S:0,0,100|T:1,12|G:0|P:0,0,0,0>\n"
    state.version = b"version = 2.1.0c\n"
    state.exchange_commands = []
    state.reject = state.drop = state.report_target = False

    def handler(sock, command):
        if command == b"model\n":
            sock.sendall(b"model = C1, 1, 4, 1\n")
        elif command == b"version\n":
            sock.sendall(state.version)
        elif command == b"M6 T2\n":
            state.exchange_commands.append(command)
            if state.drop:
                # Intentional disconnect ends this fixture server immediately.
                state.stop.set()
                sock.shutdown(socket.SHUT_RDWR)
            elif state.reject:
                sock.sendall(b"ERROR: loopback exchange refused\nok\n")
            else:
                if state.report_target:
                    state.status = state.status.replace(b"T:1,12", b"T:2,12")
                sock.sendall(b"ok\n")
        else:
            return False
        return True

    state.command_handler = handler
    panel = ToolExchangePanel(ws, storage_root=tmp_path / "exchanges", size_hint=(None, None), width=dp(650))
    ws.tool_exchange_panel = panel
    Window.add_widget(panel)
    timer = Clock.schedule_interval(lambda _dt: panel.refresh(), 0.1)
    panel.target.text = panel.target.values[1]
    try:
        pump_frames(20, sleep=0.04)
        backend.request("snapshot")
        wait_for(lambda: not backend.busy)
        yield panel, backend, ws, state, requests
    finally:
        timer.cancel()
        panel.dispose()
        Window.remove_widget(panel)


def prepared(panel):
    panel.read_identity()
    wait_for(lambda: not panel.busy)
    assert panel.identity is not None, panel.note.text
    panel.review_exchange()
    wait_for(lambda: not panel.busy)
    assert panel.review is not None, panel.note.text
    return panel.review


def test_original_identity_declared_bank_exchange_ack_then_later_tool_report_are_separate(exchange_workbench):
    panel, _backend, ws, state, requests = exchange_workbench
    ticks = []
    heartbeat = Clock.schedule_interval(lambda _dt: ticks.append(1), 0.01)
    try:
        review = prepared(panel)
        assert all(v["original_ipc_bytes_base64"] for v in panel.latest_record["responses"])
        assert state.exchange_commands == []
        assert not any(value.startswith("T8") for value in panel.target.values)
        panel.exchange_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        assert panel.latest_record["phase"] == "exchange_acknowledged", panel.note.text
        assert panel.latest_record["response"]["original_ipc_bytes_base64"]
        panel.exchange(review)
        assert state.exchange_commands == [b"M6 T2\n"]
        assert panel.observation_review is review and panel.review_action.disabled
        state.status = state.status.replace(b"T:1,12", b"T:2,12")
        wait_for(lambda: panel.latest_record["phase"] == "target_tool_reported" and not panel.busy)
        rows = [row["record"] for row in load_journal(panel.journal_path)]
        assert [r["phase"] for r in rows] == ["exchange_pending", "exchange_acknowledged", "target_tool_reported"]
        assert all(
            r["motion_completed"] is False
            and r["tool_length_verified"] is False
            and r["physical_tool_identity_verified"] is False
            for r in rows
        )
        assert rows[-1]["observation"]["state"]["last_machine_snapshot"]["status"]["tool"] == 2
        assert len([m for m, p in requests if m == "operation" and p["operation"] == "tool.change"]) == 1
        assert len(ticks) >= 5
        ws.machine.controller.executeCommand.assert_not_called()
    finally:
        heartbeat.cancel()


@pytest.mark.parametrize(
    "change", ["profile", "toolset", "cutter", "setup", "owner", "expired", "tool", "position", "spindle"]
)
def test_changed_context_or_report_never_submits_rack_exchange(exchange_workbench, change):
    panel, backend, ws, state, requests = exchange_workbench
    review = prepared(panel)
    if change == "profile":
        ws.selected_machine_profile["name"] = "Other"
    elif change == "toolset":
        ws.loaded_toolset["name"] = "Changed bank"
    elif change == "cutter":
        ws.machine.gcode_viewer.library_tool_table_mm[2].diameter = 6
    elif change == "setup":
        ws.readiness.snapshot()[1]["stock"] = [20, 20, 20]
    elif change == "owner":
        ws.control_owner.binding = None
    elif change == "expired":
        from dataclasses import replace

        panel.review = review = replace(review, created_at=review.created_at - 31)
    else:
        old, new = {
            "tool": (b"T:1,12", b"T:3,12"),
            "position": (b"MPos:1,2,3", b"MPos:2,2,3"),
            "spindle": (b"S:0,0,100", b"S:1,12000,100"),
        }[change]
        state.status = state.status.replace(old, new)
        pump_frames(20, sleep=0.04)
        backend.request("snapshot")
        wait_for(lambda: not backend.busy)
    panel.exchange(review)
    pump_frames(3)
    assert state.exchange_commands == []
    assert not any(m == "operation" and p["operation"] == "tool.change" for m, p in requests)


@pytest.mark.parametrize("failure", ["refused", "disconnect"])
def test_refused_or_lost_exchange_retains_original_result_without_retry(exchange_workbench, failure):
    panel, _backend, _ws, state, requests = exchange_workbench
    review = prepared(panel)
    state.reject = failure == "refused"
    state.drop = failure == "disconnect"
    panel.exchange(review)
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "exchange_unresolved", panel.note.text
    assert panel.latest_record["response"]["original_ipc_bytes_base64"]
    assert panel.observation_review is panel.review is None
    panel.exchange(review)
    assert len([m for m, p in requests if m == "operation" and p["operation"] == "tool.change"]) == 1
    assert state.exchange_commands == [b"M6 T2\n"]
    assert load_journal(panel.journal_path)[-1]["record"]["phase"] == "exchange_unresolved"


@pytest.mark.parametrize("change", ["intent_failure", "edit_after_intent", "retired_after_intent"])
def test_durable_intent_and_final_context_recheck_precede_wire_command(exchange_workbench, monkeypatch, change):
    import carveracontroller.desktop_tool_exchange as module

    panel, _backend, ws, state, requests = exchange_workbench
    review = prepared(panel)
    original = module.append_journal

    def journal(path, record, **kwargs):
        if record["phase"] == "exchange_pending":
            if change == "intent_failure":
                raise OSError("synthetic intent failure")
            original(path, record, **kwargs)
            if change == "edit_after_intent":
                Clock.schedule_once(lambda _dt: ws.loaded_toolset.update({"name": "Changed"}), 0)
            else:
                panel.closed = True
            return None
        return original(path, record, **kwargs)

    monkeypatch.setattr(module, "append_journal", journal)
    panel.exchange(review)
    wait_for(lambda: not panel.busy)
    assert state.exchange_commands == []
    assert not any(m == "operation" and p["operation"] == "tool.change" for m, p in requests)


def test_unsupported_firmware_local_history_export_and_responsive_layout(exchange_workbench, tmp_path):
    panel, _backend, ws, state, requests = exchange_workbench
    state.version = b"version = 2.0.0c\n"
    panel.read_identity()
    wait_for(lambda: not panel.busy)
    panel.review_exchange()
    wait_for(lambda: not panel.busy)
    assert panel.review is None and "supported" in panel.note.text
    before = [r for r in requests if r[0] != "snapshot"]
    exported = tmp_path / "exchange.json"
    ws.choose_profile_file = lambda callback, **kwargs: callback(str(exported))
    panel.export_receipt()
    wait_for(lambda: not panel.busy)
    digest = hashlib.sha256(exported.read_bytes()).hexdigest()
    panel.export_receipt()
    wait_for(lambda: not panel.busy)
    assert hashlib.sha256(exported.read_bytes()).hexdigest() == digest
    panel.inspect_attempts()
    wait_for(lambda: not panel.busy)
    assert "Historical only" in panel.note.text and [r for r in requests if r[0] != "snapshot"] == before
    for width in (320, 650, 1100):
        panel.width = dp(width)
        pump_frames(8)
        for widget in (panel.note, panel.summary):
            assert widget.height >= widget.texture_size[1]
        assert panel.identity_action.width >= dp(100)
