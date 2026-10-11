import threading
import time

from carveracontroller.machine.ui_stalls import UIStallMonitor


def test_stall_samples_are_bounded_and_recovery_is_attributed():
    now = [0.0]
    monitor = UIStallMonitor(limit=2, clock=lambda: now[0], capture=lambda _: [{"function": "blocked"}] * 40)
    for index in range(3):
        monitor.heartbeat("Setup")
        for _ in range(10):
            now[0] += 1
            monitor.check()
        monitor.heartbeat("Monitor")
    snapshot = monitor.snapshot()
    assert snapshot["evicted"] == 1
    assert [r["sequence"] for r in snapshot["records"]] == [2, 3]
    for record in snapshot["records"]:
        assert len(record["samples"]) == 3
        assert len(record["samples"][0]["stack"]) == 32
        assert record["context"] == "Setup" and record["heartbeat_gap_s"] == 10
        assert record["recovered_monotonic_s"] is not None
    snapshot["records"][-1]["samples"][0]["stack"].clear()
    assert len(monitor.snapshot()["records"][-1]["samples"][0]["stack"]) == 32
    monitor.stop()
    now[0] += 5
    monitor.check()
    assert len(monitor.snapshot()["records"]) == 2


def test_heartbeat_during_sampling_rejects_late_capture():
    now = [0.0]
    monitor = UIStallMonitor(clock=lambda: now[0])
    monitor.capture = lambda _: monitor.heartbeat("recovered") or []
    now[0] = 2
    monitor.check()
    assert monitor.snapshot()["records"] == []


def test_background_monitor_captures_target_thread_without_source_or_locals():
    monitor = UIStallMonitor(threshold=0.02)
    captured = threading.Event()
    original = monitor.capture

    def capture(thread_id):
        result = original(thread_id)
        captured.set()
        return result

    monitor.capture = capture
    monitor.start()
    worker = monitor._thread
    monitor.start()
    assert monitor._thread is worker
    assert captured.wait(2)
    deadline = time.monotonic() + 1
    while not monitor.snapshot()["records"] and time.monotonic() < deadline:
        time.sleep(0.001)
    monitor.stop()
    worker.join(1)
    assert not worker.is_alive()
    records = monitor.snapshot()["records"]
    assert records
    stack = records[0]["samples"][0]["stack"]
    assert any(
        r["function"] == "test_background_monitor_captures_target_thread_without_source_or_locals" for r in stack
    )
    assert all(set(r) == {"file", "function", "line"} and "/" not in r["file"] for r in stack)
    monitor.start()
    assert monitor._thread is worker
