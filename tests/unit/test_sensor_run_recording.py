import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.machine.run_recording import RunEvidence, packet_context, parse_numeric_fields
from carveracontroller.session_replay import replay_jsonl

BASE = "<Run|MPos:1,2,3|WPos:0,0,0|S:12000,12000,100,1,35,0,0,0,1|F:600,600,100|PWM:0.5|T:2,25|G:1|C:0,4,0,1|H:0"


def frame(seq=1, boot=10, tick=100, valid=127, extra=""):
    return BASE + f"|SE:1,{boot},1,{seq},{tick},0,{valid},1,1|SI:4,65535|SC:8,10,2,3|SA:2,20,1,-1{extra}>"


@pytest.fixture
def controller(tmp_path, monkeypatch):
    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    c = Controller(CNC(), None)
    c.stream = Mock()
    yield c
    c.stream.send.assert_not_called()
    c.stream = None


def offline_replay(controller, path):
    stream = controller.stream
    controller.stream = None
    try:
        return replay_jsonl(path)
    finally:
        controller.stream = stream


def test_packet_context_does_not_reuse_cached_values(controller):
    controller.parseBracketAngle(frame())
    assert controller.sensor_context_snapshot()["raw_inputs"]["z_motor_alarm"] is True
    assert controller.sensor_context_snapshot()["motion"]["executing_line"] == 8
    controller.parseBracketAngle("<Idle|MPos:1,2,3|WPos:0,0,0>")
    context = controller.sensor_context_snapshot()
    assert context["tool"] is None and context["spindle_temperature"] is None
    assert context["raw_inputs"]["z_motor_alarm"] is None
    assert context["motion"] is None and context["source"] is None
    assert not CNC.vars["spindle_temperature_available"]


def test_temperature_validity_is_authoritative_and_zero_can_be_real():
    state, fields = parse_numeric_fields(frame(valid=1), status=True)
    context = packet_context(state, fields, 1)
    assert context["spindle_temperature"] is None and context["power_temperature"] is None
    fields["SE"][6] = 7
    assert packet_context(state, fields, 1)["power_temperature"] == 0


@pytest.mark.parametrize("bad", ["|T:2", "|F:1", "|S:nan,2,3", "|SI:1.5,3", "|SE:1,10,2,1,0,0,1,1,1", "|SA:1,2,3,-2"])
def test_malformed_packet_is_atomic(controller, bad):
    controller.parseBracketAngle(frame())
    before = deepcopy(CNC.vars)
    previous = controller.run_evidence.latest
    malformed = "<Idle|MPos:99,99,99|WPos:0,0,0" + bad + ">"
    with pytest.raises(ValueError):
        controller.parseBracketAngle(malformed)
    assert CNC.vars == before
    assert controller.run_evidence.latest is previous


def test_source_reset_invalidates_baseline_and_reordered_source_is_rejected(controller):
    controller.parseBracketAngle(frame(seq=5, tick=500))
    controller.adaptive_monitor.baseline = {"rpm": 12000}
    with pytest.raises(ValueError, match="reordered"):
        controller.parseBracketAngle(frame(seq=4, tick=600))
    assert controller.run_evidence.latest["source"]["sequence"] == 5
    controller.parseBracketAngle(frame(seq=1, boot=11, tick=100))
    assert controller.adaptive_monitor.baseline is None
    assert controller.adaptive_monitor.quality.snapshot()["firmware_confirmed_boot_changes"] == 1


def test_event_and_diagnostic_frames_are_persisted(controller):
    controller.parseBigParentheses("{S:1,12000|P:1,0|RSSI:-55}")
    controller.parseLine("{EV:1,100,0,2,4,65535,3,2,8,10,1,2,3,12000,0.5}")
    assert len(controller.run_evidence.events) == 1
    records = [json.loads(s) for s in controller.adaptive_log_path.read_text().splitlines()]
    assert [r["kind"] for r in records] == ["diagnostic", "event"]


def test_source_sequence_gap_remains_separate_from_host_gap(controller):
    controller._evidence_arrival_override = 1
    controller.parseBracketAngle(frame(seq=1))
    controller._evidence_arrival_override = 1.2
    controller.parseBracketAngle(frame(seq=4, tick=200))
    quality = controller.adaptive_monitor.quality.snapshot()
    assert quality["firmware_missing_samples"] == 2
    assert quality["gap_count"] == 0
    assert quality["one_way_transport_delay_s"] is None


def test_program_identity_is_local_until_machine_bytes_verified(controller, tmp_path):
    path = tmp_path / "part.nc"
    path.write_text("(Operation: pocket)\nG1 X1 F600\n")
    controller.set_program_source(path, path.read_text().splitlines())
    controller._program_request("/sd/part.nc", "play requested")
    controller.parseBracketAngle(frame())
    context = controller.sensor_context_snapshot()
    assert len(context["program"]["sha256"]) == 64
    assert context["program"]["machine_file_identity"] == "unverified"
    assert context["operation"]["label"] == "Operation: pocket"


def test_offline_replay_uses_actual_parser_preserves_globals_and_never_writes(controller, tmp_path):
    controller._evidence_arrival_override = 1
    controller.parseBracketAngle(frame())
    controller._evidence_arrival_override = 1.2
    controller.parseBracketAngle(frame(seq=2, tick=200))
    before = deepcopy(CNC.vars)
    log_before = controller.adaptive_log_path.read_bytes()
    result = offline_replay(controller, controller.adaptive_log_path)
    assert result["accepted"] == 2 and result["machine_commands_sent"] == 0
    assert result["outputs"][1]["context"]["source"]["sequence"] == 2
    assert CNC.vars == before and controller.adaptive_log_path.read_bytes() == log_before
    assert len(list((tmp_path / "adaptive").glob("*.jsonl"))) == 1


def test_replay_malformed_gap_stale_alarm_and_limit(tmp_path):
    path = tmp_path / "replay.jsonl"
    records = [
        {"raw_frame": frame(), "arrival_monotonic_s": 1},
        {"raw_frame": frame(seq=3, tick=200), "arrival_monotonic_s": 3},
        {"raw_frame": "<Idle|MPos:1,2,3|WPos:0,0,0|T:2>", "arrival_monotonic_s": 3.2},
        {"raw_frame": frame(seq=4, tick=300), "arrival_monotonic_s": 3.4},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    result = replay_jsonl(path)
    assert result["accepted"] == 3 and result["rejected"] == 1
    assert result["source_quality"]["gap_count"] == 1
    assert result["outputs"][-1]["context"]["raw_inputs"]["z_motor_alarm"]
    with pytest.raises(ValueError, match="count"):
        replay_jsonl(path, max_records=2)


def test_diagnostic_packet_rejects_whole_frame(controller):
    controller.parseBigParentheses("{S:1,12000|RSSI:-55}")
    before = deepcopy(CNC.vars)
    with pytest.raises(ValueError):
        controller.parseBigParentheses("{S:0,0|E:0,0}")
    assert CNC.vars == before


def test_evidence_commands_do_not_reach_machine(controller, tmp_path):
    controller.parseBracketAngle(frame())
    path = tmp_path / "export.json"
    controller.executeCommand("evidence status")
    controller.executeCommand("evidence export " + str(path))
    assert json.loads(path.read_text())["frames"][0]["raw_frame"] == frame()


def test_event_dump_receipt_preserves_original_boot_and_reports_missing_frames(controller):
    controller.parseLine("{EH:1,9,1,1,5}")
    controller.parseLine("{EV:5,100,0,2,4,65535,3,2,8,10,1,2,3,12000,0.5,15,2,3,25}")
    controller.parseLine("{EE:0}")
    receipt = controller.run_evidence.dump_receipts[-1]
    assert receipt["complete"] and receipt["header"]["boot_id"] == 9
    event = controller.run_evidence.events[-2]
    assert event["event"]["rpm"] == 12000 and event["source_header"]["boot_id"] == 9
    controller.parseLine("{EH:1,8,1,1,5}")
    controller.parseLine("{EE:0}")
    assert not controller.run_evidence.dump_receipts[-1]["complete"]


def test_source_invalid_spindle_does_not_refresh_advisory_sample(controller):
    controller.parseBracketAngle(frame())
    previous = controller.adaptive_monitor.last
    controller.parseBracketAngle(frame(seq=2, tick=200, valid=126))
    assert controller.adaptive_monitor.last is previous
    assert controller.adaptive_monitor.quality.snapshot()["latest_missing"] == ["S_validity"]


def test_fresh_diagnostic_commands_and_physical_declarations_reach_sample(controller):
    controller._evidence_arrival_override = 1
    controller.measurement_context_provider = lambda: {"assembly_id": "tool-A", "seat_revision": 2}
    controller.parseBigParentheses("{F:1,80|R:1|V:1,100|G:1}")
    controller._evidence_arrival_override = 1.2
    controller.parseBracketAngle(frame())
    context = controller.adaptive_monitor.last.context
    assert context["assembly_id"] == "tool-A" and context["seat_revision"] == 2
    assert context["accessory_commands"]["diagnostic_commands"]["air"] == [1]
    controller._evidence_arrival_override = 4
    controller.parseBracketAngle(frame(seq=2, tick=200))
    assert controller.adaptive_monitor.last.context["accessory_commands"]["diagnostic_commands"]["air"] is None


def test_control_actions_replay_and_persistence_failure_is_reported(controller, monkeypatch):
    controller._evidence_arrival_override = 1
    assert controller.adaptiveCommand("adaptive baseline")
    assert (
        "baseline armed" in offline_replay(controller, controller.adaptive_log_path)["outputs"][0]["advisory"]["reason"]
    )
    monkeypatch.setattr("carveracontroller.Controller.MAX_EVIDENCE_LOG_BYTES", 1)
    assert controller.adaptiveCommand("adaptive off") is False
    assert controller._adaptive_log_failed


def prepare_recovery(controller, tmp_path, lines):
    from carveracontroller.machine.recovery_policy import RecoveryVerification

    path = tmp_path / "resume.nc"
    path.write_text("".join(lines))
    controller.set_program_source(path, lines)
    controller._get_line_position_from_gcode_viewer = lambda _: (1, 2, -3, None)
    controller._evidence_arrival_override = 1
    controller.parseBracketAngle(frame().replace("<Run", "<Idle").replace("|G:1", "|G:1|R:0"))
    controller.playStartLineCommand("/sd/resume.nc", len(lines), preview=True, lines=lines)
    assessment = controller.recovery_assessment(len(lines))
    controller._recovery_verification = RecoveryVerification(
        assessment["scope"], True, True, True, True, -1.5, "Reference, clearance and exact SD program checked", True
    )


def test_recovery_verification_binds_program_lines_and_filename(controller, tmp_path):
    lines = ["G21 G90\n", "G55\n", "G1 X1 F600\n", "G1 X2\n"]
    prepare_recovery(controller, tmp_path, lines)
    assert controller.recovery_assessment(4)["allowed"]
    changed = lines[:]
    changed[2] = "G1 X20 F600\n"
    assert controller.playStartLineCommand("/sd/resume.nc", 4, lines=changed) is False
    assert controller.playStartLineCommand("/sd/other.nc", 4, lines=lines) is False


def test_recovery_approach_uses_verified_clearance_and_restores_inch_incremental_modes(controller, tmp_path):
    lines = ["G20 G91\n", "G55\n", "G1 X1 F10\n", "G1 X2\n"]
    prepare_recovery(controller, tmp_path, lines)
    commands = controller.playStartLineCommand("/sd/resume.nc", 4, preview=True, lines=lines)
    safe = commands.index("buffer G53 G0 Z-1.5")
    xy = commands.index("buffer G0 X1.000 Y2.000")
    descent = commands.index("buffer G1 Z-3.000")
    assert commands[safe - 1] == "buffer G21 G90" and safe < xy < descent
    assert "buffer G1 F254" in commands[safe:descent]
    assert commands[descent + 1 : descent + 4] == ["buffer G20", "buffer G91", "buffer G1 F10"]


def test_recovery_verification_replays_without_motion(controller, tmp_path):
    lines = ["G21 G90\n", "G55\n", "G1 X1 F600\n", "G1 X2\n"]
    prepare_recovery(controller, tmp_path, lines)
    from dataclasses import asdict

    payload = {"start_line": 4, **asdict(controller._recovery_verification)}
    controller._evidence_arrival_override = 1.1
    assert controller.recoveryCommand("recovery verify " + json.dumps(payload))
    result = offline_replay(controller, controller.adaptive_log_path)
    assert result["outputs"][-1]["recovery"]["allowed"]


def test_replay_refuses_connected_machine(controller):
    controller.parseBracketAngle(frame())
    with pytest.raises(ValueError, match="disconnected"):
        replay_jsonl(controller.adaptive_log_path)


def test_native_inch_status_is_normalized_only_when_unit_flag_is_present():
    state, fields = parse_numeric_fields(frame().replace("|C:0,4,0,1", "|C:0,4,1,1"), status=True)
    fields["MPos"].append(90)
    context = packet_context(state, fields, 1)
    assert context["machine_position"] == [25.4, 50.8, 76.19999999999999, 90]
    assert context["commanded_feed_mm_min"] == 15240
    fields.pop("C")
    unknown = packet_context(state, fields, 1)
    assert unknown["machine_position"] is None and unknown["commanded_feed_mm_min"] is None
    assert unknown["raw_fields"]["MPos"] == [1, 2, 3, 90]


def test_execute_command_does_not_restart_stopped_receive_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), None)
    controller.stream = Mock()
    controller.stop.set()
    assert controller.executeCommand("diagnose")
    assert controller.stop.is_set()
    controller.stream = None
    controller.stop.clear()


@pytest.mark.parametrize("prefix", [["G54\n"], ["G55\n", "M6 T3\n"]])
def test_recovery_requires_prepared_tool_and_origin(controller, tmp_path, prefix):
    lines = ["G21 G90\n", *prefix, "G1 X1 F600\n", "G1 X2\n"]
    prepare_recovery(controller, tmp_path, lines)
    assert controller.playStartLineCommand("/sd/resume.nc", len(lines), lines=lines) is False


def test_recovery_restores_live_modes_when_program_has_no_explicit_modes(controller, tmp_path):
    lines = ["G55\n", "G1 X1 F10\n", "G1 X2\n"]
    prepare_recovery(controller, tmp_path, lines)
    controller.run_evidence.latest["modes"] = [0, 4, 1, 0]
    commands = controller.playStartLineCommand("/sd/resume.nc", 3, preview=True, lines=lines)
    assert commands[-4:] == ["buffer G20", "buffer G91", "buffer G1 F10", "resume"]


def test_background_diagnostics_poll_without_popup_and_preserve_transfer_pause(monkeypatch, tmp_path):
    from carveracontroller import Controller as module

    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), None)
    controller.stream = Mock()
    controller.stream.waiting_for_recv.side_effect = lambda: controller.stop.set() or False
    controller.comms = Mock(ready=True)
    controller.stop.clear()
    clock = iter([0, 3])
    monkeypatch.setattr(module.time, "time", lambda: next(clock))
    monkeypatch.setattr(module.time, "sleep", lambda _: controller.stop.set())
    status, diagnostic = Mock(), Mock()
    monkeypatch.setattr(controller, "viewStatusReport", status)
    monkeypatch.setattr(controller, "viewDiagnoseReport", diagnostic)
    controller.streamIO()
    diagnostic.assert_called_once_with(True)
    assert not controller.diagnosing
    controller.stop.clear()
    controller.sendNUM = 1
    clock = iter([0, 3])
    diagnostic.reset_mock()
    controller.streamIO()
    diagnostic.assert_not_called()
    controller.stream = None
    controller.stop.clear()


def test_raw_probe_hits_are_dispatched_and_replayable(controller):
    controller._evidence_arrival_override = 1
    raw = "{PRH:1,10,1,1,100,0,1,1,2,3,1,7,10,3,0}"
    controller.parseLine(raw)
    assert controller.log.get_nowait() == (controller.MSG_NORMAL, raw)
    result = offline_replay(controller, controller.adaptive_log_path)
    assert result["accepted"] == 1


def test_firmware_measurement_ages_distinguish_uart_receipt_from_acquisition():
    state, fields = parse_numeric_fields(frame(extra="|ST:1,7,50000,100000,200000|W:3.4"), status=True)
    context = packet_context(state, fields, 1)
    assert context["measurement_ages"]["spindle_temperature"]["age_us"] == 50000
    assert context["measurement_ages"]["probe_voltage"]["age_us"] == 200000
    assert "radio acquisition unknown" in context["measurement_ages"]["probe_voltage"]["basis"]
    fields["ST"] = [1, 0, 4294967295, 4294967295, 4294967295]
    unavailable = packet_context(state, fields, 2)
    assert unavailable["probe_voltage"] is None and unavailable["spindle_temperature"] is None


def test_failed_reconnect_preserves_local_program_identity_and_invalidates_remote_claim(controller, tmp_path):
    path = tmp_path / "program.nc"
    lines = ["G21 G90\n", "G1 X1 F600\n"]
    path.write_text("".join(lines))
    program = controller.set_program_source(path, lines)
    controller.run_evidence.program["machine_file_identity"] = "operator verified"
    controller.stream = None
    controller.wifi_stream = Mock()
    controller.wifi_stream.open.return_value = False
    from carveracontroller.Controller import CONN_WIFI

    assert controller.open(CONN_WIFI, "invalid.example") is False
    assert controller.run_evidence.program["sha256"] == program["sha256"]
    assert controller.run_evidence.program["machine_file_identity"] == "unverified"
    controller.stream = Mock()  # fixture preserves a transport send assertion
