import json
import threading
import time

from carveracontroller.machine.telemetry_log import TelemetryLog


def test_stalled_storage_is_bounded_and_shutdown_reports_pending(tmp_path, monkeypatch):
    writer = TelemetryLog(tmp_path / "telemetry.jsonl", capacity=2)
    entered, release = threading.Event(), threading.Event()
    original = writer._write

    def blocked(record):
        entered.set()
        assert release.wait(5)
        original(record)

    monkeypatch.setattr(writer, "_write", blocked)
    record = {"sample": {"rpm": 12000}}
    try:
        assert writer.submit(record)
        assert entered.wait(1)
        record["sample"]["rpm"] = 1
        assert writer.submit({"sample": {"rpm": 11900}})
        assert not writer.submit({"sample": {"rpm": 11800}})
        start = time.monotonic()
        receipt = writer.close(0.02)
        assert time.monotonic() - start < 0.3
        assert receipt["inflight"] == 1 and receipt["queued"] == 1
        assert not receipt["drained"] and receipt["rejected"] == 1
        assert not writer.submit({})
    finally:
        release.set()
    receipt = writer.drain(2)
    assert receipt["drained"] and receipt["written"] == 2
    assert receipt["rejected"] == 2 and receipt["failed"] == 0
    records = [json.loads(line) for line in writer.path.read_text().splitlines()]
    assert [item["sample"]["rpm"] for item in records] == [12000, 11900]


def test_write_failure_counts_abandoned_records_and_does_not_retry(tmp_path, monkeypatch):
    errors = []
    writer = TelemetryLog(tmp_path / "telemetry.jsonl", on_error=errors.append)
    entered, release = threading.Event(), threading.Event()

    def fail(record):
        entered.set()
        assert release.wait(5)
        raise OSError("storage unavailable")

    monkeypatch.setattr(writer, "_write", fail)
    try:
        writer.submit({"packet": 1})
        assert entered.wait(1)
        writer.submit({"packet": 2})
        writer.submit({"packet": 3})
    finally:
        release.set()
    receipt = writer.close(2)
    assert receipt["failed"] == 3 and receipt["written"] == 0 and receipt["drained"]
    assert receipt["error"] == "OSError: storage unavailable"
    assert not writer.submit({"packet": 4})
    assert writer.snapshot()["rejected"] == 1
    # Callback is outside the state lock and may finish just after drain.
    deadline = time.monotonic() + 1
    while not errors and time.monotonic() < deadline:
        time.sleep(0.001)
    assert errors == ["OSError: storage unavailable"]


def test_idle_worker_restarts_and_keeps_record_order(tmp_path):
    writer = TelemetryLog(tmp_path / "telemetry.jsonl")
    assert writer.submit({"packet": 1})
    assert writer.drain(2)["written"] == 1
    thread = writer._thread
    thread.join(2)
    assert not thread.is_alive()
    assert writer.submit({"packet": 2})
    assert writer.close(2)["written"] == 2
    assert [json.loads(line)["packet"] for line in writer.path.read_text().splitlines()] == [1, 2]


def test_saved_records_expose_gaps_after_queue_saturation(tmp_path, monkeypatch):
    writer = TelemetryLog(tmp_path / "telemetry.jsonl", capacity=1)
    entered, release = threading.Event(), threading.Event()
    original = writer._write

    def blocked(record):
        entered.set()
        assert release.wait(5)
        original(record)

    monkeypatch.setattr(writer, "_write", blocked)
    try:
        assert writer.submit({"packet": 1})
        assert entered.wait(1)
        assert not writer.submit({"packet": 2})
    finally:
        release.set()
    assert writer.drain(2)["written"] == 1
    assert writer.submit({"packet": 3})
    receipt = writer.close(2)
    assert receipt["attempted"] == 3 and receipt["rejected"] == 1
    records = [json.loads(line) for line in writer.path.read_text().splitlines()]
    assert records[-1]["persistence"] == {"sequence": 3, "rejected_before": 1, "failed_before": 0}
