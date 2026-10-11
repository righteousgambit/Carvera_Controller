"""Local startup evidence uses actual owned pipes and never connects a CNC."""

import hashlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.headless import RUNTIME_VERSION
from carveracontroller.headless.client import ClientUnavailable, SupervisorClient
from carveracontroller.headless.startup_receipts import StartupReceipt, interval_ms


@pytest.mark.parametrize("start,end", [(None, 1), (1, None), (2, 1), (float("nan"), 1), (0, float("inf"))])
def test_unavailable_or_regressing_clock_does_not_invent_a_duration(start, end):
    assert interval_ms(start, end) is None


def test_receipt_retains_separate_launch_ready_and_total_timing_and_rejects_late_ready():
    receipt = StartupReceipt()
    receipt.begin(5, 10)
    receipt.process_created_at_s = 10.1
    receipt.wait_started_at_s = 10.2
    receipt.accepted(10.3, "a" * 64)
    receipt.finish("ready", 10.4)
    view = receipt.snapshot(12, None)
    assert view["process_launch_ms"] == pytest.approx(100)
    assert view["ready_wait_ms"] == pytest.approx(200)
    assert view["total_startup_ms"] == pytest.approx(400)
    assert view["elapsed_ms"] == pytest.approx(400)
    assert view["configured_ready_wait_limit_s"] == 5
    receipt.accepted(99, "b" * 64)
    assert receipt.snapshot(99, 1)["ready_event_sha256"] == "a" * 64
    timed_out = StartupReceipt()
    timed_out.begin(5, 20)
    timed_out.finish("timed_out", 25, "readiness_wait_timed_out")
    timed_out.accepted(26, "c" * 64)
    assert timed_out.snapshot(27, -15)["ready_received_at_s"] is None


def child(script):
    return SupervisorClient("127.0.0.1", argv=[sys.executable, "-u", "-c", script])


def test_exit_during_observation_cannot_report_running_alongside_an_exit_code():
    client = SupervisorClient("127.0.0.1")
    client._process = SimpleNamespace(pid=123, poll=Mock(side_effect=[None, 7]))
    first = client.snapshot()
    assert first["running"] is True and first["startup"]["process_returncode"] is None
    second = client.snapshot()
    assert second["running"] is False and second["startup"]["process_returncode"] == 7


def test_actual_validated_ready_bytes_are_hashed_and_startup_remains_historical_after_close():
    raw = (
        json.dumps(
            {"event": "ready", "runtime_version": RUNTIME_VERSION, "connection_owned": False, "protocol": "smoothie"}
        )
        + "\n"
    )
    client = child("import sys; sys.stdout.write(" + repr(raw) + "); sys.stdout.flush(); sys.stdin.read()")
    try:
        client.start()
        view = client.snapshot()
        startup = view["startup"]
        assert view["ready"] and startup["phase"] == "ready"
        assert startup["ready_event_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
        assert 0 <= startup["process_launch_ms"] <= startup["total_startup_ms"]
        assert startup["ready_wait_ms"] >= 0
        startup["phase"] = "corrupted detached view"
    finally:
        client.close()
    after = client.snapshot()
    assert not after["running"] and not after["ready"]
    assert after["startup"]["phase"] == "ready" and after["startup"]["process_returncode"] == 0
    assert after["startup"]["cnc_connection_or_motion_verified"] is False
    assert all(not worker.is_alive() for worker in client._threads)


@pytest.mark.parametrize(
    "script,code",
    [
        ("print('bad protocol',flush=True)", "readiness_protocol_failed"),
        ("raise SystemExit(7)", "child_ended_before_ready"),
    ],
)
def test_actual_failed_child_preserves_cause_exit_code_and_no_retry(script, code):
    client = child(script)
    with pytest.raises(ClientUnavailable):
        client.start()
    report = client.snapshot()["startup"]
    assert report["phase"] == "failed" and report["failure_code"] == code
    assert report["ready_received_at_s"] is None and report["ready_event_sha256"] is None
    assert report["process_returncode"] == (0 if code == "readiness_protocol_failed" else 7)
    with pytest.raises(ClientUnavailable):
        client.start()
    assert client.snapshot()["startup"] == report


def test_wait_timeout_and_stderr_volume_are_retained_without_log_contents():
    client = child("import sys; sys.stderr.write('diagnostic marker'); sys.stderr.flush(); sys.stdin.read()")
    with pytest.raises(ClientUnavailable, match="startup timed out"):
        client.start(timeout=0.1)
    view = client.snapshot()
    assert view["startup"]["phase"] == "timed_out"
    assert view["startup"]["configured_ready_wait_limit_s"] == 0.1
    assert view["startup"]["stderr_bytes_drained"] == len("diagnostic marker")
    assert view["startup"]["stderr_retained"] is False
    assert "diagnostic marker" not in json.dumps(view)
