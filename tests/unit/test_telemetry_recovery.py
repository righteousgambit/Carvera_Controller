import hashlib
import io
import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from carveracontroller.machine.telemetry_log import TelemetryLog
from carveracontroller.machine.telemetry_recovery import TelemetryRecovery


def failed_writer(tmp_path, monkeypatch):
    writer = TelemetryLog(tmp_path / "failed.jsonl")
    writer.path.write_bytes(b"partial failed record")
    monkeypatch.setattr(writer, "_write", Mock(side_effect=OSError("disk full")))
    assert writer.submit({"packet": 1})
    assert writer.drain(2)["failed"] == 1
    assert not writer.submit({"packet": 2})
    return writer


def wait_recovery(recovery):
    deadline = time.monotonic() + 3
    while recovery.snapshot()["current"]["state"] == "pending" and time.monotonic() < deadline:
        time.sleep(0.005)
    assert recovery.snapshot()["current"]["state"] != "pending"
    return recovery.snapshot()["current"]


def test_blocked_recovery_is_single_and_retains_failed_bytes_and_final_gap(tmp_path, monkeypatch):
    previous = failed_writer(tmp_path, monkeypatch)
    recovery = TelemetryRecovery()
    entered, release = threading.Event(), threading.Event()
    real = TelemetryLog._write
    new = []

    def blocked(writer, record):
        if record.get("record_type") == "telemetry_recovery_gap":
            entered.set()
            assert release.wait(3)
        real(writer, record)

    def publish(writer, operation):
        boundary = {
            "record_type": "telemetry_recovery_boundary",
            "operation_id": operation,
            "previous": previous.snapshot(),
        }
        assert writer.submit(boundary)
        previous.close(0)
        new.append(writer)
        return boundary

    monkeypatch.setattr(TelemetryLog, "_write", blocked)
    try:
        assert recovery.start(previous, tmp_path, publish)
        assert entered.wait(1)
        operation = recovery.snapshot()["current"]["operation_id"]
        assert not recovery.start(previous, tmp_path, publish)
        assert recovery.snapshot()["current"]["operation_id"] == operation
        assert not previous.submit({"packet": 3})
        assert not new
    finally:
        release.set()
    receipt = wait_recovery(recovery)
    assert receipt["state"] == "resumed" and receipt["boundary"]["previous"]["rejected"] == 2
    assert new[0].submit({"packet": 4})
    assert new[0].close(2)["written"] == 3
    records = [json.loads(line) for line in new[0].path.read_text().splitlines()]
    assert records[0]["record_type"] == "telemetry_recovery_gap"
    assert records[0]["previous"]["rejected"] == 1
    assert records[0]["complete_run"] is False
    assert records[1] == {
        **receipt["boundary"],
        "persistence": {"sequence": 2, "rejected_before": 0, "failed_before": 0},
    }
    assert records[2]["packet"] == 4
    assert (
        hashlib.sha256(new[0].path.read_bytes().splitlines(keepends=True)[0]).hexdigest()
        == receipt["gap_record_sha256"]
    )
    assert previous.path.read_bytes() == b"partial failed record"


@pytest.mark.parametrize("failure", ["readback", "write", "closed", "owner"])
def test_failed_or_closed_recovery_cannot_publish(tmp_path, monkeypatch, failure):
    previous = failed_writer(tmp_path, monkeypatch)
    recovery = TelemetryRecovery()
    publish = Mock(return_value=None if failure == "owner" else {"boundary": True})
    if failure == "readback":
        original = Path.open

        def corrupt(path, *args, **kwargs):
            if path.name.startswith("telemetry-recovery-") and args and args[0] == "rb":
                return io.BytesIO(b"{}")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", corrupt)
    elif failure == "write":
        monkeypatch.setattr(TelemetryLog, "_write", Mock(side_effect=OSError("still full")))
    elif failure == "closed":
        recovery.close()
        assert not recovery.start(previous, tmp_path, publish)
        publish.assert_not_called()
        return
    assert recovery.start(previous, tmp_path, publish)
    receipt = wait_recovery(recovery)
    assert receipt["state"] == "failed" and receipt["error"]
    assert Path(receipt["path"]).exists()  # Failed attempts remain inspectable.
    assert previous.path.read_bytes() == b"partial failed record"
    if failure != "owner":
        publish.assert_not_called()


def test_healthy_writer_does_not_start_recovery(tmp_path):
    writer = TelemetryLog(tmp_path / "healthy.jsonl")
    recovery = TelemetryRecovery()
    assert not recovery.start(writer, tmp_path, Mock())
    assert recovery.snapshot()["current"] is None


def test_retry_keeps_failed_attempt_and_uses_a_distinct_segment(tmp_path, monkeypatch):
    previous = failed_writer(tmp_path, monkeypatch)
    recovery = TelemetryRecovery()
    real = TelemetryLog._write
    monkeypatch.setattr(TelemetryLog, "_write", Mock(side_effect=OSError("still full")))
    publish = Mock(return_value={"boundary": True})
    assert recovery.start(previous, tmp_path, publish)
    failed = wait_recovery(recovery)
    assert failed["state"] == "failed"
    failed_path = Path(failed["path"])
    retained = failed_path.read_bytes()
    monkeypatch.setattr(TelemetryLog, "_write", real)
    assert recovery.start(previous, tmp_path, publish)
    resumed = wait_recovery(recovery)
    assert resumed["state"] == "resumed"
    assert resumed["operation_id"] != failed["operation_id"]
    assert resumed["path"] != failed["path"]
    assert recovery.snapshot()["history"] == [failed]
    assert failed_path.read_bytes() == retained
    assert previous.path.read_bytes() == b"partial failed record"
    publish.assert_called_once()
    publish.call_args.args[0].close(2)


def test_controller_recovery_retains_loss_counts_and_never_sends_commands(tmp_path, monkeypatch):
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    monkeypatch.setitem(CNC.vars, "state", "Idle")
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    previous = controller._adaptive_log = failed_writer(tmp_path, monkeypatch)
    controller.adaptive_log_path = previous.path
    before = controller.adaptive_monitor.enabled
    assert controller.resume_telemetry_logging()
    receipt = wait_recovery(controller._telemetry_recovery)
    assert receipt["state"] == "resumed"
    assert controller._adaptive_log is not previous
    assert controller.telemetry_persistence()["prior_lost_records"] == 2
    controller._observe_adaptive({"S": [12000, 12000, 100], "F": [0, 600, 100], "MPos": [0, 0, 0]})
    result = controller.stop_telemetry_logging()
    assert result["written"] == 3
    records = [json.loads(line) for line in controller.adaptive_log_path.read_text().splitlines()]
    assert records[0]["record_type"] == "telemetry_recovery_gap"
    assert records[1]["prior_lost_records"] == 2
    assert records[2]["packet_complete"] is True
    assert not controller.resume_telemetry_logging()
    assert before == controller.adaptive_monitor.enabled
    controller.stream.send.assert_not_called()


@pytest.mark.parametrize("change", ["connection", "shutdown"])
def test_controller_rejects_pending_recovery_after_owner_change(tmp_path, monkeypatch, change):
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    previous = controller._adaptive_log = failed_writer(tmp_path, monkeypatch)
    controller.adaptive_log_path = previous.path
    entered, release = threading.Event(), threading.Event()
    real = TelemetryLog._write

    def blocked(writer, record):
        entered.set()
        assert release.wait(3)
        real(writer, record)

    monkeypatch.setattr(TelemetryLog, "_write", blocked)
    try:
        assert controller.resume_telemetry_logging() and entered.wait(1)
        if change == "connection":
            with controller._adaptive_lock:
                controller._connection_generation += 1
        else:
            assert controller.stop_telemetry_logging(0)["error"]
    finally:
        release.set()
    receipt = wait_recovery(controller._telemetry_recovery)
    assert receipt["state"] == "failed"
    assert controller._adaptive_log is previous
    assert previous.path.read_bytes() == b"partial failed record"
    controller.stop_telemetry_logging(0)
    controller.stream.send.assert_not_called()
