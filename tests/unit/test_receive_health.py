from carveracontroller.machine.receive_health import ReceiveHealth


def test_poll_wire_and_status_have_independent_evidence_and_detached_exports():
    health = ReceiveHealth(7, 10)
    health.stage("loop", 11, loop=True)
    health.poll(12)
    health.wire(80, 13)
    health.wire(0, 14)
    health.status(14)
    health.stage("parsing bytes", 15)
    record = health.snapshot(18)
    assert record["loop_age_s"] == 7
    assert record["poll_age_s"] == 6
    assert record["wire_age_s"] == 5
    assert record["valid_status_age_s"] == 4
    assert record["stage_age_s"] == 3
    assert record["bytes_received"] == 80
    assert record["polls_sent"] == record["valid_status_packets"] == 1
    record["recent_errors"].append({"error_class": "invented"})
    assert health.snapshot(18)["recent_errors"] == []


def test_error_history_is_bounded_and_never_retains_exception_payloads():
    health = ReceiveHealth(1, 10)
    health.stage("receiving bytes", 10)
    for now in range(100):
        health.error(OSError("private socket payload"), 10 + now)
    record = health.snapshot(120)
    assert record["receive_errors"] == 100
    assert len(record["recent_errors"]) == 32
    assert "private socket payload" not in str(record)
    assert record["valid_status_age_s"] is None
    assert health.snapshot(float("nan"))["stage_age_s"] is None


def test_host_write_calls_have_bounded_detached_history_and_no_delivery_inference():
    import pytest

    health = ReceiveHealth(4, 1)
    health.write("command", 8, 1.1, 1.15, True)
    health.write("realtime", 1, 1.3, 1.32, False, "OSError")
    result = health.snapshot(2)["control_writes"]
    assert result["total_calls"] == 2 and result["failed_calls"] == 1
    assert result["last_call_ms"] == pytest.approx(20)
    assert result["mean_call_ms"] == pytest.approx(35)
    assert result["p95_call_ms"] == pytest.approx(50)
    assert result["last_call_age_s"] == pytest.approx(0.68)
    assert result["delivery_verified"] is False
    assert result["acknowledgment_latency_ms"] is None and result["physical_response_ms"] is None
    assert result["recent_calls"][0]["requested_bytes"] == 8
    result["recent_calls"][0]["duration_ms"] = 999
    assert health.snapshot(2)["control_writes"]["recent_calls"][0]["duration_ms"] == pytest.approx(50)
    for now in range(100):
        health.write("command", 2, 2 + now, 2.1 + now, True)
    result = health.snapshot(110)["control_writes"]
    assert result["total_calls"] == 102 and result["window_calls"] == 64
    assert result["connection_generation"] == 4
    assert all("command" not in row and "payload" not in row for row in result["recent_calls"])


def test_invalid_write_clocks_and_exception_payloads_are_not_exported_as_timing():
    import json

    health = ReceiveHealth(1, 1)
    for start, end in ((2, 1), (float("nan"), 3), (3, float("inf")), (True, 3)):
        health.write("file_initiation", True, start, end, False, "OSError: private payload")
    result = health.snapshot(4)["control_writes"]
    assert result["total_calls"] == result["failed_calls"] == 4
    assert result["mean_call_ms"] is None and result["last_call_age_s"] is None
    assert all(row["duration_ms"] is None and row["requested_bytes"] is None for row in result["recent_calls"])
    assert "private payload" not in json.dumps(result, allow_nan=False)
    health.write("untracked", 1, 1, 2, True)
    assert health.snapshot(4)["control_writes"]["total_calls"] == 4
