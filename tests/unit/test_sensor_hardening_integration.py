"""Production integration regressions: durability, cancellation and probe custody."""

import ast
import json
import threading
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import carveracontroller.Controller as controller_module
from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.machine.probe_evidence import ProbeEvidenceStore, parse_latched_contact, setter_trends
from carveracontroller.machine.recovery_policy import RecoveryVerification

PROGRAM = ["G21 G90 G17 G94\n", "G55\n", "T2 M6\n", "M3 S12000\n", "M9\n", "G0 X1 Y2 Z-3\n", "G1 F600\n", "G1 X2\n"]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    controller = Controller(CNC(), None)
    controller.adaptive_log_path = tmp_path / "run.jsonl"
    path = tmp_path / "job.nc"
    path.write_text("".join(PROGRAM))
    controller._evidence_arrival_override = 1.0
    controller.set_program_source(path, PROGRAM)
    controller._program_request("/sd/job.nc", "review")
    controller._evidence_arrival_override = 1.0
    context = {
        "firmware_boot_id": 9,
        "wcs": 1,
        "tool": 2,
        "tlo": 25,
        "rotation": 0,
        "work_position": [0, 0, -10],
        "machine_position": [10, 20, -20],
        "work_offset": [10, 20, -10],
        "modes": [0, 4, 0, 1],
        "machine_filename": "/sd/job.nc",
        "halt_reason": 0,
        "state": "Idle",
        "telemetry_stale": False,
        "raw_inputs": {"cover": True},
    }
    monkeypatch.setattr(controller, "_recovery_context", lambda: dict(context))
    callbacks = []

    def schedule(callback, _delay):
        handle = Mock()
        callbacks.append((callback, handle))
        return handle

    monkeypatch.setattr(controller_module, "Clock", SimpleNamespace(schedule_once=schedule))
    monkeypatch.setattr(
        controller_module,
        "App",
        SimpleNamespace(
            get_running_app=lambda: SimpleNamespace(
                is_community_firmware=True, fw_version_digitized=controller_module.Utils.digitize_v("9.0.0")
            )
        ),
    )
    assessment = controller.recovery_assessment(8)
    controller._recovery_verification = RecoveryVerification(
        assessment["scope"], True, True, True, True, -5, "Tool, origin, machine file and path checked", True
    )
    controller.stream = Mock()
    yield controller, context, callbacks
    controller.stream = None
    controller._cancel_pending_recovery("test teardown")
    if controller._evidence_writer:
        controller._evidence_writer.close(2)


def test_review_uses_program_boundary_and_never_viewer_cache_or_transport(rig):
    controller, _, _ = rig
    controller._get_line_position_from_gcode_viewer = Mock(side_effect=AssertionError("stale viewer consulted"))
    plan = controller.recovery_preview("/sd/job.nc", 8, lines=PROGRAM, clearance_machine_z_mm=-5)
    commands = plan["commands"]
    assert commands.index("buffer G53 G0 Z-5.000000") < commands.index("buffer G0 X1.000000 Y2.000000")
    assert commands.index("buffer M3 S12000.000000") < commands.index("buffer G1 Z-3.000000")
    assert "buffer M6" not in commands
    controller.stream.send.assert_not_called()


@pytest.mark.parametrize("cancel", ["stop", "operator", "realtime", "alarm", "changed pose", "timeout"])
def test_delayed_recovery_cannot_survive_cancellation(rig, cancel):
    controller, context, callbacks = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    assert controller.stream.send.call_count == 2
    callback, handle = callbacks[-1]
    if cancel == "stop":
        controller.stopRun()
    elif cancel == "operator":
        controller.executeCommand("G0 X4")
    elif cancel == "realtime":
        controller.executeRealtime(ord("!"))
    elif cancel == "alarm":
        controller.parseLine("ALARM: axis error")
    elif cancel == "changed pose":
        context["work_position"] = [1, 0, -10]
    else:
        controller._evidence_arrival_override = 100
    count = controller.stream.send.call_count
    context["state"] = "Pause"
    assert callback(0) is False
    sent = [call.args[0] for call in controller.stream.send.call_args_list[count:]]
    assert all(b"abort -R " in payload for payload in sent)
    assert not controller._recovery_pending_active
    if cancel in ("stop", "operator", "realtime", "alarm"):
        handle.cancel.assert_called_once()


def test_fresh_pause_executes_once_and_old_callback_cannot_repeat(rig):
    controller, context, callbacks = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    callback, _ = callbacks[-1]
    context["state"] = "Pause"
    assert callback(0) is True
    count = controller.stream.send.call_count
    assert count > 2
    assert callback(0) is False
    assert controller.stream.send.call_count == count


def test_new_request_owns_timer_and_old_timer_cannot_execute(rig):
    controller, context, callbacks = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    old, handle = callbacks[-1]
    assert not controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    handle.cancel.assert_called_once()
    context["state"] = "Pause"
    count = controller.stream.send.call_count
    assert old(0) is False
    assert controller.stream.send.call_count == count
    assert controller._recovery_disposal_nonce is not None


def test_disk_failure_does_not_activate_operator_verification_or_advisory(rig, monkeypatch):
    controller, _, _ = rig
    payload = dict(asdict(controller._recovery_verification), start_line=8)
    controller._recovery_verification = None
    monkeypatch.setattr(controller, "_write_evidence", lambda *args, **kwargs: False)
    assert not controller.recoveryCommand("recovery verify " + json.dumps(payload))
    assert controller._recovery_verification is None
    old = controller.adaptive_monitor
    old.enabled = False
    assert not controller.adaptiveCommand("adaptive shadow")
    assert controller.adaptive_monitor is old and not old.enabled
    controller.stream.send.assert_not_called()


def test_evidence_export_cannot_replace_live_journal(rig):
    controller, _, _ = rig
    assert controller._evidence_writer.flush(2)
    original = controller.adaptive_log_path.read_bytes()
    assert not controller.evidenceCommand("evidence export " + str(controller.adaptive_log_path))
    assert controller.adaptive_log_path.read_bytes() == original


def test_controller_stop_events_are_instance_local():
    first, second = Controller(CNC(), None), Controller(CNC(), None)
    first.stopRun()
    assert first.stop.is_set() and not second.stop.is_set()
    second.clearRun()
    assert first.stop.is_set()


@pytest.mark.parametrize("control", ["command", "disconnect"])
def test_concurrent_operator_command_stops_recovery_before_next_write(rig, control):
    controller, context, callbacks = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    context["state"] = "Pause"
    sent, threads = [], []

    def send(payload):
        sent.append(payload)
        if b"goto " in payload:
            action = (lambda: controller.executeCommand("G0 X999")) if control == "command" else controller.close_manual
            thread = threading.Thread(target=action)
            threads.append(thread)
            thread.start()
            assert controller._recovery_cancel_event.wait(2)

    controller.stream.send.side_effect = send
    assert callbacks[-1][0](0) is False
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert len(sent) == 2
    assert b"goto " in sent[0] and b"abort -R " in sent[1]
    assert all(b"G0 X999" not in payload and b"resume" not in payload for payload in sent)
    assert controller._recovery_disposal_nonce is not None


def test_disposal_requires_matching_ack_and_subsequent_valid_idle(rig):
    controller, _, _ = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    controller.stopRun()
    controller.clearRun()
    nonce = controller._recovery_disposal_nonce
    idle = "<Idle|MPos:10,20,-20|WPos:0,0,-10|C:0,4,0,1>"
    controller.parseLine(idle)
    controller.parseLine(f"{{RB:1,{nonce % 0xFFFFFFFF + 1}}}")
    assert not controller.executeCommand("resume")
    assert not controller.recovery_assessment(8)["allowed"]
    controller.parseLine(f"{{RB:1,{nonce}}}")
    assert controller._recovery_disposal_ack
    assert not controller.executeCommand("G0 X1")
    controller.parseLine("<Idle|C:0,4,0,1>")  # missing pose never closes the gate
    assert controller._recovery_disposal_nonce == nonce
    controller.parseLine(idle.replace("Idle", "Pause"))
    assert controller._recovery_disposal_nonce == nonce
    controller.parseLine(idle)
    assert controller._recovery_disposal_nonce is None
    assert controller._recovery_verification is None
    assert controller.executeCommand("G0 X1")


def test_disposal_send_failure_blocks_motion_and_file_until_retry(rig):
    controller, _, _ = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    controller.stream.send.side_effect = OSError("transport failed")
    controller.stopRun()
    nonce = controller._recovery_disposal_nonce
    controller.stream.send.side_effect = None
    count = controller.stream.send.call_count
    assert not controller.executeFileCommand("upload /sd/a.nc")
    assert not controller.executeCommand("play /sd/a.nc")
    assert controller.stream.send.call_count == count
    assert controller.abortCommand()
    assert controller.stream.send.call_args.args[0] == controller.comms.encode_command(f"abort -R {nonce}\n".encode())


def test_file_transfer_cancels_recovery_and_cannot_race_stale_buffer(rig):
    controller, _, callbacks = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    assert not controller.executeFileCommand("download /sd/a.nc")
    assert b"abort -R " in controller.stream.send.call_args.args[0]
    assert callbacks[-1][0](0) is False


@pytest.mark.parametrize("line", [";" + "x" * 128 + "\n", ";" + "é" * 64 + "\n", ";hidden\0tail\n"])
def test_recovery_refuses_oversized_physical_lines(rig, line):
    controller, _, _ = rig
    with pytest.raises(ValueError, match="physical-line limit"):
        controller.recovery_preview("/sd/job.nc", 8, lines=[line] + PROGRAM[1:], clearance_machine_z_mm=-5)
    controller.stream.send.assert_not_called()


def test_recovery_validates_stored_crlf_byte_lengths(rig):
    controller, _, _ = rig
    program = [";" + "x" * 126 + "\n"] + PROGRAM
    path = Path(controller.run_evidence.program["local_path"])
    path.write_bytes("".join(program).replace("\n", "\r\n").encode())
    controller.set_program_source(path, program)
    with pytest.raises(ValueError, match="Stored line 1"):
        controller.recovery_preview("/sd/job.nc", 9, lines=program, clearance_machine_z_mm=-5)


def test_recovery_requires_prepared_absolute_mode(rig):
    controller, context, _ = rig
    context["modes"] = [0, 4, 0, 0]
    with pytest.raises(ValueError, match="Prepare absolute G90"):
        controller.recovery_preview("/sd/job.nc", 8, lines=PROGRAM, clearance_machine_z_mm=-5)


def test_halt_disposal_allows_explicit_unlock_but_never_queued_motion(rig):
    controller, _, _ = rig
    assert controller.playStartLineCommand("/sd/job.nc", 8, lines=PROGRAM)
    controller.parseLine("ALARM: halted")
    assert controller.executeCommand("$X")
    assert not controller.executeCommand("$X\nG0 X99")
    assert controller.abortCommand()
    assert controller._recovery_disposal_nonce is not None


def test_live_event_waits_for_recorder_restart_and_reaches_new_journal(rig):
    controller, _, _ = rig
    assert controller._evidence_writer.close(2)
    entered, release, reader_started = threading.Event(), threading.Event(), threading.Event()

    class OldWriter:
        def status(self):
            return {"error": None, "closed": True, "dropped": 0, "pending_records": 0}

        def flush(self, timeout_s):
            return True

        def close(self, timeout_s):
            entered.set()
            assert release.wait(2)
            return True

        def pending_records(self):
            return []

        def submit(self, record):
            raise AssertionError("Event reached closed old writer")

    controller._evidence_writer = OldWriter()
    restart_results = []
    restart = threading.Thread(target=lambda: restart_results.append(controller.evidenceCommand("evidence restart")))
    restart.start()
    assert entered.wait(2)

    def receive():
        reader_started.set()
        controller.parseLine("{EH:1,9,1,0,0}")

    reader = threading.Thread(target=receive)
    reader.start()
    assert reader_started.wait(2)
    release.set()
    for thread in (restart, reader):
        thread.join(2)
        assert not thread.is_alive()
    assert restart_results == [True]
    assert controller._evidence_writer.flush(2)
    records = [json.loads(line) for line in controller.adaptive_log_path.read_text().splitlines()]
    assert any(record.get("kind") == "event_header" for record in records)
    assert controller._evidence_writer.status()["dropped"] == 0


def test_resume_review_precedes_every_pre_job_effect():
    path = Path(controller_module.__file__).with_name("main.py")
    tree = ast.parse(path.read_text())
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_play_now")
    scope = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), scope)
    machine = SimpleNamespace(open_resume_playback_confirm_popup=Mock(), controller=Mock())
    scope["_play_now"](machine, "/sd/job.nc", 8)
    machine.open_resume_playback_confirm_popup.assert_called_once_with("/sd/job.nc", 8)
    assert not machine.controller.mock_calls


def test_stale_lock_is_ignored_and_process_restart_append_is_durable(tmp_path):
    path = tmp_path / "probe.jsonl"
    path.with_suffix(".lock").write_text("crashed owner")
    first = ProbeEvidenceStore(path)
    first.append("measurement_setup", context={})
    second = ProbeEvidenceStore(path)
    second.append("measurement_setup", context={"probe_identity": "TP06"})
    assert len(second.events()) == 2
    assert second.last_receipt["durable"] and second.last_receipt["readback"]
    assert path.with_suffix(".lock").read_text() == "crashed owner"


def test_changed_setup_during_measurement_is_retained_and_cannot_correct(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "probe.jsonl")
    store.begin({"probe_identity": "TP06-a"})
    raw = store.capture("probe", {"x_diameter": 25}, {"probe_identity": "TP06-b"})
    assert raw["setup_changed"]
    assert store.events()[0]["context"]["probe_identity"] == "TP06-a"
    assert store.events()[0]["end_context"]["probe_identity"] == "TP06-b"


@pytest.mark.parametrize(
    "raw",
    [
        "x{PRH:1,9,1,0,0,0,1,0,0,0,0,0,0,0,0}",
        "{PRH:1,0,1,0,0,0,1,0,0,0,0,0,0,0,0}",
        "{PRH:1,9,1,0,0,0,1,0,0,0,0,0,-1,0,0}",
    ],
)
def test_malformed_contact_is_not_a_valid_raw_hit(raw):
    with pytest.raises(ValueError):
        parse_latched_contact(raw)


def test_setter_view_ignores_unusable_receipts_instead_of_crashing():
    base = {"kind": "measurement", "result_kind": "setter", "context": {}, "result": {}}
    assert setter_trends([base, dict(base, context=[], result={"measurements": []})]) == []


def test_recorder_failure_restart_preserves_pending_and_original_journal(rig, monkeypatch):
    from carveracontroller.machine import evidence_io

    controller, _, _ = rig
    writer = controller._evidence_writer
    assert writer.flush(2)
    old_path = controller.adaptive_log_path
    old_bytes = old_path.read_bytes()
    original_append = evidence_io.append_jsonl
    monkeypatch.setattr(evidence_io, "append_jsonl", Mock(side_effect=OSError("injected disk failure")))
    record = {"kind": "alarm", "raw_frame": "ERROR: test", "arrival_monotonic_s": 2}
    assert controller._write_evidence(record, background=True)
    assert not writer.flush(2)
    assert controller.sensor_context_snapshot()["recording"]["write_failed"]
    monkeypatch.setattr(evidence_io, "append_jsonl", original_append)
    assert controller.evidenceCommand("evidence restart")
    assert old_path.read_bytes() == old_bytes
    assert controller.adaptive_log_path != old_path
    sidecars = list(old_path.parent.glob(old_path.name + ".pending-*.json"))
    assert len(sidecars) == 1
    assert json.loads(sidecars[0].read_text())["records"] == [record]
    assert not controller.sensor_context_snapshot()["recording"]["write_failed"]


def test_failed_pending_sidecar_keeps_original_writer_and_records(rig, monkeypatch):
    from carveracontroller.machine import evidence_io

    controller, _, _ = rig
    writer = controller._evidence_writer
    assert writer.flush(2)
    old_path = controller.adaptive_log_path
    original_append = evidence_io.append_jsonl
    monkeypatch.setattr(evidence_io, "append_jsonl", Mock(side_effect=OSError("injected append failure")))
    record = {"kind": "alarm", "raw_frame": "ERROR: test", "arrival_monotonic_s": 2}
    assert controller._write_evidence(record, background=True)
    assert not writer.flush(2)
    monkeypatch.setattr(evidence_io, "append_jsonl", original_append)
    monkeypatch.setattr(evidence_io, "write_json_atomic", Mock(side_effect=OSError("injected sidecar failure")))
    assert not controller.evidenceCommand("evidence restart")
    assert controller._evidence_writer is writer
    assert controller.adaptive_log_path == old_path
    assert writer.pending_records() == [record]


def test_shutdown_closes_writer_admission_after_durable_flush(rig):
    controller, _, _ = rig
    assert controller.shutdown_evidence()
    assert controller._evidence_writer.status()["closed"]
    assert not controller._evidence_writer.submit({"kind": "after shutdown"})


def test_overlapping_command_after_failed_receipt_is_not_attributed_as_clean(tmp_path, monkeypatch):
    store = ProbeEvidenceStore(tmp_path / "probe.jsonl")
    store.command("G38.2 Z-1 F60", {"probe_identity": "TP06-a"})
    store.feed("#151 = 1.23")
    append = store.append
    monkeypatch.setattr(store, "append", Mock(side_effect=OSError("injected receipt failure")))
    with pytest.raises(OSError):
        store.command("G38.2 X-1 F60", {"probe_identity": "TP06-b"})
    store.feed("#152 = 4.56")
    monkeypatch.setattr(store, "append", append)
    event = store.capture("incomplete", {"reason": "overlap"})
    assert event["session_contaminated"]
    assert event["context"]["probe_identity"] == "TP06-a"
    assert event["superseding_commands"][0]["context"]["probe_identity"] == "TP06-b"
    assert len(event["raw_console"]) == 2


def test_shutdown_preserves_interrupted_probe_session_and_failed_journal(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "probe.jsonl")
    store.command("G38.2 Z-1 F60", {"probe_identity": "TP06"})
    store.feed("#151 = 1.23")
    event = store.shutdown_pending()
    assert event["result_kind"] == "incomplete"
    assert store.shutdown_pending() is None
    store.command("G38.2 Z-2 F60", {"probe_identity": "TP06"})
    store.feed("#151 = 2.34")
    original = store.path.read_bytes() + b"unfinished"
    store.path.write_bytes(original)
    pending = store.shutdown_pending()
    assert store.path.read_bytes() == original
    recovered = json.loads(Path(pending["pending_preserved"]).read_text())
    assert recovered["kind"] == "pending_measurement"
    assert recovered["raw_console"][0]["text"] == "#151 = 2.34"
