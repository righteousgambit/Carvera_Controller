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
