import hashlib
import json
import socket
from pathlib import Path
from unittest.mock import Mock

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.popup import Popup

from carveracontroller.desktop_probe_settings import ProbeSettingsPanel
from carveracontroller.machine.probe_settings_workflow import KEYS, append_journal, load_journal
from tests.integration import test_backend_job_file as job_fixture
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for

backend_job = job_fixture.backend_job


@pytest.fixture
def probe_workbench(backend_job, tmp_path):
    _job, backend, ws, state, requests, _setup = backend_job
    ws.selected_machine_profile.update({"name": "Loopback test Carvera", "model": "C1"})
    state.status = state.status.replace(b"C:0,4,0,1", b"C:1,4,0,1")
    pump_frames(20, sleep=0.04)
    backend.request("snapshot")
    wait_for(lambda: not backend.busy)
    values = {KEYS[0]: "2.0000", KEYS[1]: "-0.1250"}
    state.fail_second = False
    state.lose_ack = False
    state.config_writes = []

    def command(sock, raw):
        parts = raw.decode().strip().split()
        if len(parts) < 3 or parts[0] not in ("config-get", "config-set"):
            return False
        key = parts[2]
        assert parts[1] == "sd" and key in KEYS
        if parts[0] == "config-set":
            state.config_writes.append(raw)
            if state.lose_ack:
                values[key] = parts[3]
                # End the fixture server before queued observations can write
                # into the socket deliberately closed without acknowledgement.
                state.stop.set()
                sock.shutdown(socket.SHUT_RDWR)
                return True
            if state.fail_second and key == KEYS[1]:
                sock.sendall(b"ERROR: synthetic second write failure\n")
            else:
                values[key] = parts[3]
                sock.sendall(f"sd: {key} has been set to {values[key]}\r\n".encode())
        else:
            text = f"sd: {key} is set to {values[key]}" if key in values else f"sd: {key} is not in config"
            sock.sendall((text + "\r\n").encode())
        return True

    state.command_handler = command
    panel = ProbeSettingsPanel(ws, storage_root=tmp_path / "probe", size_hint=(None, None), width=dp(650))
    Window.add_widget(panel)
    panel.name.text = "Bench probe"
    panel.tip.text, panel.correction.text = "2.01", "0.0000"
    timer = Clock.schedule_interval(lambda _dt: panel.refresh(), 0.1)
    try:
        yield panel, backend, ws, state, requests, values
    finally:
        timer.cancel()
        panel.dispose()
        Window.remove_widget(panel)


def read(panel):
    panel.read_settings()
    wait_for(lambda: not panel.busy)
    assert panel.baseline is not None, panel.note.text


def review(panel):
    def current_review_context():
        try:
            panel._binding(write=True)
        except ValueError:
            return False
        return True

    # Reading the SD settings is not a fresh machine-status observation.
    # Establish the actual write-admission context before reviewing once;
    # this does not retry review application or issue configuration writes.
    wait_for(current_review_context)
    panel.review_settings()
    assert panel.review is not None, panel.note.text
    pump_frames(3)
    # Rendering the local review may advance the observation age. Return with
    # current admission evidence before the test changes or applies that review.
    wait_for(current_review_context)


def test_actual_child_original_fixed_settings_review_apply_durable_readback_and_responsive_ui(probe_workbench):
    panel, _backend, ws, state, requests, values = probe_workbench
    ticks = []
    heartbeat = Clock.schedule_interval(lambda _dt: ticks.append(1), 0.01)
    try:
        read(panel)
        original = panel.latest_record
        assert original["settings"][KEYS[1]]["original_numeric_token"] == "-0.1250"
        assert original["response"]["original_ipc_bytes_base64"]
        assert state.config_writes == []
        review(panel)
        panel.apply_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        assert panel.latest_record["phase"] == "reported_sd_values_match", panel.note.text
        assert values == {KEYS[0]: "2.01", KEYS[1]: "0.0000"}
        rows = load_journal(panel.journal_path)
        assert [r["record"]["phase"] for r in rows] == ["apply_pending", "reported_sd_values_match"]
        result = rows[-1]["record"]["response"]["envelope"]["result"]
        assert len(result["command_receipts"]) == 6
        assert result["active_settings_verified"] is False and result["physical_accuracy_verified"] is False
        assert panel.baseline is panel.review is None
        assert [m for m, _p in requests if m.startswith("probe")] == ["probe_profile_read", "probe_profile_apply"]
        assert len(ticks) >= 5
        ws.machine.controller.executeCommand.assert_not_called()
    finally:
        heartbeat.cancel()


@pytest.mark.parametrize("change", ["draft", "profile", "owner", "expiry", "spindle", "model"])
def test_changed_review_never_submits_application(probe_workbench, change):
    panel, backend, ws, state, requests, _values = probe_workbench
    read(panel)
    review(panel)
    reviewed = panel.review
    if change == "draft":
        panel.tip.text = "2.02"
    elif change == "profile":
        ws.selected_machine_profile["name"] = "Different machine"
    elif change == "owner":
        ws.control_owner.binding = None
    elif change == "expiry":
        from dataclasses import replace

        panel.review = reviewed = replace(reviewed, created_at=reviewed.created_at - 31)
    else:
        state.status = (
            state.status.replace(b"S:0,0,100", b"S:1,12000,100")
            if change == "spindle"
            else state.status.replace(b"C:1,4,0,1", b"C:2,4,0,1")
        )
        backend.request("snapshot")
        wait_for(lambda: not backend.busy)
        pump_frames(20, sleep=0.04)
        backend.request("snapshot")
        wait_for(lambda: not backend.busy)
    panel.apply_settings(reviewed)
    pump_frames(4)
    assert not any(m == "probe_profile_apply" for m, _p in requests)
    assert state.config_writes == []


def test_partial_write_receipts_retained_no_retry_then_new_read_required(probe_workbench):
    panel, _backend, _ws, state, requests, values = probe_workbench
    read(panel)
    review(panel)
    old = panel.review
    state.fail_second = True
    panel.apply_settings(old)
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "apply_unresolved", panel.note.text
    assert values[KEYS[0]] == "2.01" and values[KEYS[1]] == "-0.1250"
    record = load_journal(panel.journal_path)[-1]["record"]
    assert record["response"]["original_ipc_bytes_base64"]
    assert len(record["response"]["envelope"]["completed_command_receipts"]) >= 3
    assert panel.baseline is panel.review is None and "No retry" in panel.note.text
    panel.apply_settings(old)
    assert len([m for m, _p in requests if m == "probe_profile_apply"]) == 1
    assert panel.baseline is panel.review is None and "review again" in panel.note.text
    state.fail_second = False
    read(panel)
    assert panel.baseline["settings"][KEYS[0]]["original_numeric_token"] == "2.01"


def test_producer_rereads_baseline_before_any_write(probe_workbench):
    panel, _backend, _ws, state, _requests, values = probe_workbench
    read(panel)
    review(panel)
    values[KEYS[0]] = "2.0"
    panel.apply_settings(panel.review)
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "apply_unresolved"
    assert state.config_writes == []
    assert panel.baseline is None


@pytest.mark.parametrize("change", ["intent_failure", "draft_after_intent", "closed_after_intent"])
def test_intent_durability_and_final_ui_context_gate_precede_application(probe_workbench, monkeypatch, change):
    import carveracontroller.desktop_probe_settings as module

    panel, _backend, _ws, state, requests, _values = probe_workbench
    read(panel)
    review(panel)
    original = module.append_journal

    def journal(path, record, **kwargs):
        if record["phase"] == "apply_pending":
            if change == "intent_failure":
                raise OSError("synthetic intent failure")
            original(path, record, **kwargs)
            if change == "draft_after_intent":
                # Queue edit before the worker's final admission callback.
                Clock.schedule_once(lambda _dt: setattr(panel.tip, "text", "2.02"), 0)
            else:
                panel.closed = True
            return None
        return original(path, record, **kwargs)

    monkeypatch.setattr(module, "append_journal", journal)
    panel.apply_settings(panel.review)
    wait_for(lambda: not panel.busy)
    assert not any(m == "probe_profile_apply" for m, _p in requests)
    assert state.config_writes == []


def test_local_presets_import_export_and_unresolved_recovery_never_replay(probe_workbench, tmp_path):
    panel, _backend, ws, _state, requests, _values = probe_workbench
    before = len(requests)
    panel.tip.text = "1e-9"
    panel.save_preset()
    assert panel.tip.error and not panel.store.path.exists()
    panel.tip.text = "2.01"
    panel.save_preset()
    wait_for(lambda: not panel.busy)
    assert panel.presets[0]["name"] == "Bench probe"
    panel.tip.text = "8"
    panel.saved.text = "Bench probe"
    assert panel.tip.text == "2.01"
    target = tmp_path / "presets-export.json"
    ws.choose_profile_file = lambda callback, **_kwargs: callback(str(target))
    panel._pick("presets")
    wait_for(lambda: not panel.busy)
    assert json.loads(target.read_text())["presets"] == panel.presets
    incoming = tmp_path / "presets-import.json"
    item = dict(panel.presets[0], name="Second probe", tip_diameter_token="2.03")
    incoming.write_text(json.dumps({"schema": 1, "presets": [item]}))
    ws.choose_profile_file = lambda callback, **_kwargs: callback(str(incoming))
    panel._pick("import")
    wait_for(lambda: not panel.busy)
    assert panel.presets == [item]
    attempt = panel.root_path / "receipts" / "uncertain.jsonl"
    append_journal(attempt, {"phase": "apply_pending", "submitted": "unknown"}, new=True)
    append_journal(panel.root_path / "receipts" / "unsupported.jsonl", {"phase": ["invalid"]}, new=True)
    raw = attempt.read_bytes()
    panel.inspect_attempts()
    wait_for(lambda: not panel.busy)
    assert "apply_pending" in panel.note.text and "no replay" in panel.note.text
    assert "unsupported phase" in panel.note.text
    assert attempt.read_bytes() == raw
    assert all(method == "snapshot" for method, _p in requests[before:])


def test_lost_acknowledgement_retains_unknown_result_without_retry(probe_workbench):
    panel, _backend, _ws, state, requests, values = probe_workbench
    read(panel)
    review(panel)
    state.lose_ack = True
    panel.apply_settings(panel.review)
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "apply_unresolved"
    assert values[KEYS[0]] == "2.01" and values[KEYS[1]] == "-0.1250"
    record = load_journal(panel.journal_path)[-1]["record"]
    assert record["submitted"] is True and record["response"]["original_ipc_bytes_base64"]
    assert record["response"]["envelope"]["error"] == "unknown_outcome"
    assert len([m for m, _p in requests if m == "probe_profile_apply"]) == 1
    assert len(state.config_writes) == 1 and panel.baseline is panel.review is None


def test_late_admission_callback_cannot_submit_after_worker_timeout(probe_workbench, monkeypatch):
    import carveracontroller.desktop_probe_settings as module

    panel, _backend, _ws, state, requests, _values = probe_workbench
    read(panel)
    review(panel)
    original, delayed = module.Clock.schedule_once, []

    def schedule(callback, timeout=0):
        if callback.__name__ == "preflight":
            delayed.append(callback)
            return None
        return original(callback, timeout)

    monkeypatch.setattr(module.Clock, "schedule_once", schedule)
    panel.apply_settings(panel.review)
    wait_for(lambda: not panel.busy)
    assert len(delayed) == 1
    delayed[0](0)
    pump_frames(3)
    assert panel.latest_record["phase"] == "not_submitted"
    assert not any(m == "probe_profile_apply" for m, _p in requests)
    assert state.config_writes == []


def test_result_durability_failure_retains_response_and_requires_new_read(probe_workbench, monkeypatch):
    import carveracontroller.desktop_probe_settings as module

    panel, _backend, _ws, state, _requests, values = probe_workbench
    read(panel)
    review(panel)
    original = module.append_journal

    def journal(path, record, **kwargs):
        if record["phase"] == "reported_sd_values_match":
            raise OSError("synthetic result durability failure")
        return original(path, record, **kwargs)

    monkeypatch.setattr(module, "append_journal", journal)
    panel.apply_settings(panel.review)
    wait_for(lambda: not panel.busy)
    assert values == {KEYS[0]: "2.01", KEYS[1]: "0.0000"}
    assert panel.latest_record["response"]["original_ipc_bytes_base64"]
    assert load_journal(panel.journal_path)[-1]["record"]["phase"] == "apply_pending"
    assert panel.baseline is panel.review is None and "Result durability unavailable" in panel.summary.text
    assert len(state.config_writes) == 2 and not panel.receipt_action.disabled


def test_owner_change_after_read_retains_original_receipt_without_arming_baseline(probe_workbench, monkeypatch):
    import carveracontroller.desktop_probe_settings as module

    panel, _backend, ws, _state, requests, _values = probe_workbench
    original = module.validate_read

    def validate(value, connection):
        result = original(value, connection)
        ws.control_owner.binding = None
        return result

    monkeypatch.setattr(module, "validate_read", validate)
    panel.read_settings()
    wait_for(lambda: not panel.busy)
    assert panel.baseline is None and "read current settings again" in panel.note.text
    assert panel.latest_record["response"]["original_ipc_bytes_base64"]
    assert not any(m == "probe_profile_apply" for m, _p in requests)


@pytest.mark.parametrize("width", [320, 650, 1100])
def test_probe_pane_navigation_and_layout_in_actual_workbench(kivy_app, tmp_path, monkeypatch, width):
    from carveracontroller.desktop_commands import workspace_commands

    ws = kivy_app.root.desktop_workspace
    operator_path = Path.home() / ".carvera" / "probe-settings" / "presets.json"
    operator_before = hashlib.sha256(operator_path.read_bytes()).hexdigest() if operator_path.exists() else None
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    commands = {c.id: c for c in workspace_commands(ws)}
    assert commands["machine.task.probe"].invoke()
    deck = ws.machine_tasks
    assert deck.active == "Probe"
    parent = deck.parent
    parent.remove_widget(deck)
    popup = Popup(content=deck, size_hint=(None, None), size=(dp(width + 28), dp(760)))
    popup.open(animation=False)
    try:
        pump_frames(8)
        panel = ws.probe_settings_panel
        assert panel.parent is deck.sections["Probe"]
        assert panel.local_actions.cols == (1 if width == 320 else 2)
        assert deck.navigation.height == dp(34) and deck.scroll.height > dp(500)
        assert panel.read_action.disabled  # disconnected backend, no accidental RPC
        # Capture mounted panel for visual review, independent of live hardware.
        target = tmp_path / f"probe-pane-{width}.png"
        deck.export_to_png(str(target))
        send.assert_not_called()
        operator_after = hashlib.sha256(operator_path.read_bytes()).hexdigest() if operator_path.exists() else None
        assert operator_after == operator_before
    finally:
        popup.dismiss(animation=False)
        if deck.parent is not None:
            deck.parent.remove_widget(deck)
        parent.add_widget(deck)
        deck.show("Connect")
        pump_frames(3)
