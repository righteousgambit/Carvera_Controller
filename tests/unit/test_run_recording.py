import json
from unittest.mock import Mock

import pytest

from carveracontroller.machine.run_recording import RecordingReplay, RunRecording, load_recording, selected_context


def test_gap_reconnect_and_retention_remain_explicit_in_roundtrip():
    record = RunRecording(capacity=4)
    record.capture_status("Run", {"P": [80, 10, 1], "S": [11950, 12000]}, 10, 1000, 1)
    record.capture_status("Run", {"P": [100, 20, 2]}, 13, 1003, 1)
    record.capture_status("Idle", {"T": [2, 40]}, 14, 1004, 2)
    loaded = load_recording(record.export_bytes())
    assert loaded["dropped_events"] == 1
    assert [event["kind"] for event in loaded["events"]] == ["gap", "status", "connection_boundary", "status"]
    assert loaded["events"][0]["data"]["duration_seconds"] == 3
    assert loaded["events"][1]["data"]["fields"] == {"P": [100, 20, 2]}
    assert "executed_line" not in loaded["events"][1]["data"]
    assert loaded["events"][2]["data"]["previous_generation"] == 1


def test_capture_and_snapshot_do_not_share_packet_storage():
    record = RunRecording()
    fields = {"MPos": [1, 2, 3], "WPos": [4, 5, 6], "C": [0, 4, 1, 1]}
    record.capture_status("Idle", fields, 10, 1000, 1)
    fields["MPos"][0] = 99
    snapshot = record.snapshot()
    assert snapshot["events"][0]["data"]["fields"]["MPos"] == [1, 2, 3]
    snapshot["events"][0]["data"]["fields"].clear()
    assert record.snapshot()["events"][0]["data"]["fields"]["C"] == [0, 4, 1, 1]


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True])
def test_bad_packet_is_rejected_without_losing_last_valid_record(invalid):
    record = RunRecording()
    record.capture_status("Idle", {"T": [1, 40]}, 10, 1000, 1)
    before = record.export_bytes()
    with pytest.raises(ValueError):
        record.capture_status("Run", {"S": [invalid]}, 11, 1001, 1)
    assert record.export_bytes() == before


def test_corruption_and_duplicate_keys_do_not_enter_replay():
    record = RunRecording()
    record.capture_status("Idle", {}, 10, 1000, 1)
    archive = json.loads(record.export_bytes())
    archive["payload"]["events"][0]["data"]["state"] = "Run"
    with pytest.raises(ValueError, match="digest"):
        load_recording(json.dumps(archive).encode())
    with pytest.raises(ValueError, match="Duplicate"):
        load_recording(b'{"payload":{},"payload":{},"sha256":""}')


def test_replay_seeks_observations_without_extrapolating_gaps_or_reconnects():
    record = RunRecording()
    record.capture_status("Run", {"MPos": [1, 2, 3]}, 10, 1000, 1)
    record.capture_status("Run", {"MPos": [2, 2, 3]}, 11, 1001, 1)
    record.capture_status("Hold", {"MPos": [7, 2, 3]}, 15, 1005, 1)
    record.capture_status("Idle", {"MPos": [8, 2, 3]}, 17, 1007, 2)
    replay = RecordingReplay(record.export_bytes())
    assert replay.at(9)["sample"] is None and replay.at(18)["sample"] is None
    assert replay.at(10.5)["sample"]["data"]["fields"]["MPos"] == [1, 2, 3]
    assert replay.at(10.5)["age_seconds"] == 0.5
    assert replay.at(12)["sample"] is None  # Entire unobserved gap stays unknown.
    assert replay.at(16)["sample"] is None  # Connection boundary stays unknown.
    assert replay.at(15)["sample"]["data"]["state"] == "Hold"
    assert replay.at(17)["sample"]["data"]["state"] == "Idle"


def test_transport_capture_uses_one_packet_clock_and_never_inherits_missing_fields(monkeypatch):
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    controller = Controller(CNC(), lambda _: None)
    send = Mock()
    monkeypatch.setattr(controller, "executeCommand", send)
    controller.parseBracketAngle("<Run|MPos:1,2,3|WPos:4,5,6|S:11950,12000,100|F:100,200,100|P:80,10,1>")
    first = controller.run_recording.snapshot()["events"][-1]
    assert first["monotonic_at"] == controller.observed_pose.timestamp
    assert first["data"]["fields"]["P"] == [80, 10, 1]
    controller.parseBracketAngle("<Idle|MPos:1,2,3|WPos:4,5,6>")
    last = controller.run_recording.snapshot()["events"][-1]
    assert "S" not in last["data"]["fields"] and "P" not in last["data"]["fields"]
    assert load_recording(controller.run_recording.export_bytes())["events"][-1] == last
    send.assert_not_called()


def test_recorded_marker_requires_same_packet_units_and_supported_rotary_pose():
    record = RunRecording()
    for index, fields in enumerate(
        (
            {"MPos": [1, 2, 3], "C": [0, 4, 1, 1]},
            {"MPos": [1, 2, 3]},
            {"MPos": [1, 2, 3, 90], "C": [0, 4, 0, 1]},
            {"MPos": [1, 2, 3, 0], "C": [0, 4, 0, 1]},
        )
    ):
        record.capture_status("Idle", fields, index + 10, index + 1000, 1)
    replay = RecordingReplay(record.export_bytes())
    assert replay.machine_point(0) == pytest.approx((25.4, 50.8, 76.2))
    assert replay.machine_point(1) is None
    assert replay.machine_point(2) is None
    assert replay.machine_point(3) == (1, 2, 3)
    assert replay.machine_point(-1) is None


def test_bound_recording_retains_exact_program_and_declared_setup_without_rebinding_old_packets(tmp_path):
    from hashlib import sha256

    path = tmp_path / "cut.nc"
    path.write_bytes(b"G21\r\nG1 X1\r\n")
    setup = {
        "work_offset_mm": [-1, -2, -3],
        "stock_origin_mm": [0, 0, 0],
        "stock_size_mm": [10, 20, 5],
        "alignment_confirmed": False,
    }
    context = selected_context(path, setup)
    record = RunRecording(context=context)
    context["setup"]["work_offset_mm"][0] = 99
    record.capture_status("Idle", {}, 10, 1000, 1)
    loaded = load_recording(record.export_bytes())
    assert loaded["schema"] == 2
    assert loaded["context"]["program"]["sha256"] == sha256(path.read_bytes()).hexdigest()
    assert loaded["context"]["setup"]["work_offset_mm"] == [-1, -2, -3]
    path.write_text("changed")
    setup["work_offset_mm"][0] = 99
    assert record.snapshot()["context"] == loaded["context"]
    assert load_recording(RunRecording().export_bytes())["schema"] == 1
    invalid = selected_context(path, setup)
    invalid["setup"]["stock_size_mm"] = [-1, 20, 5]
    with pytest.raises(ValueError, match="positive"):
        RunRecording(context=invalid)
