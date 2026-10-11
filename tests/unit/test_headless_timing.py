"""Exact phase arithmetic and connection-bound, bounded diagnostic custody."""

from math import inf, nan

import pytest

from carveracontroller.headless.timing import CommandTiming, TransportDiagnostics


def timing(*, outcome="controller_acknowledged", connection="c"):
    return CommandTiming(1, 1.2, 1.25, 1.27, 1.5).finish(1.6, connection, outcome)


def test_exact_queue_write_ack_and_return_phases_do_not_claim_physical_latency():
    row = timing()
    assert row["command_queue_ms"] == pytest.approx(200)
    assert row["dispatch_to_send_ms"] == pytest.approx(50)
    assert row["send_call_ms"] == pytest.approx(20)
    assert row["send_start_to_ack_ms"] == pytest.approx(250)
    assert row["ack_to_return_ms"] == pytest.approx(100)
    assert row["total_ms"] == pytest.approx(600)
    assert row["acknowledged_at_s"] == 1.5
    assert row["ack_observed_during_send"] is False
    assert row["firmware_sample_age_ms"] is None
    assert row["one_way_network_latency_ms"] is None
    assert row["physical_response_ms"] is None
    assert row["motion_completed"] is False


def test_ack_can_arrive_before_sendall_returns_without_negative_or_clamped_durations():
    row = CommandTiming(1, 1.1, 1.2, 1.4, 1.3).finish(1.5, "c", "controller_acknowledged")
    assert row["clock_state"] == "valid" and row["ack_observed_during_send"] is True
    assert row["send_call_ms"] == pytest.approx(200)
    assert row["send_start_to_ack_ms"] == pytest.approx(100)
    assert row["ack_to_return_ms"] == pytest.approx(200)


@pytest.mark.parametrize("probe", [CommandTiming(1, 1.1), CommandTiming(1, 1.1, 1.2), CommandTiming(1, 1.1, 1.2, 1.3)])
def test_unknown_outcome_never_fabricates_an_acknowledgment(probe):
    row = probe.finish(2, "c", "unknown_outcome")
    assert row["clock_state"] == "valid"
    assert row["acknowledged_at_s"] is None and row["send_start_to_ack_ms"] is None
    assert row["physical_response_ms"] is None and row["ack_to_return_ms"] is None


@pytest.mark.parametrize(
    "probe,now",
    [
        (CommandTiming(2, 1), 3),
        (CommandTiming(1, 2, 1.5), 3),
        (CommandTiming(1, 2, None, 2.5), 3),
        (CommandTiming(1, 2, 2.5, 2.4), 3),
        (CommandTiming(1, 2, 2.5, None, 2.4), 3),
        (CommandTiming(1, 2, 2.5, None, 4), 3),
        (CommandTiming(nan, 2), 3),
        (CommandTiming(1, 2), inf),
        (CommandTiming(True, 2), 3),
    ],
)
def test_bad_clock_evidence_cannot_publish_phase_values(probe, now):
    import json

    row = probe.finish(now, "c", "controller_acknowledged")
    assert row["clock_state"] == "invalid"
    assert row["clock_issue"] in ("timestamp_order", "unsupported_timestamp")
    assert all(v is None for k, v in row.items() if k.endswith(("_ms", "_at_s")))
    json.dumps(row, allow_nan=False)


def test_recent_window_is_bounded_and_retains_all_outcomes_without_raw_commands():
    health = TransportDiagnostics()
    health.reset("c")
    for index in range(70):
        assert health.record_command(timing(outcome="unknown_outcome" if index < 5 else "controller_acknowledged"))
    result = health.snapshot(2)
    assert result["total_commands"] == 70 and result["window_commands"] == 64
    assert result["outcomes"]["unknown_outcome"] == 0
    assert result["mean_send_start_to_ack_ms"] == pytest.approx(250)
    assert result["p95_send_start_to_ack_ms"] == pytest.approx(250)
    assert all("command" not in row for row in result["recent_commands"])
    result["recent_commands"][0]["outcome"] = "modified"
    assert health.snapshot(2)["outcomes"]["controller_acknowledged"] == 64


def test_new_connection_cannot_reuse_old_observations_or_command_latency():
    health = TransportDiagnostics()
    health.reset("c")
    assert health.record_command(timing())
    health.observation("status", 1, {"state": "Idle", "spindle_rpm": 12000, "spindle_target_rpm": 12000})
    health.reset("new")
    assert health.record_command(timing()) is False
    result = health.snapshot(2)
    assert result["total_commands"] == 0 and result["recent_commands"] == []
    assert result["status_arrivals"]["state"] == "unavailable"
    assert result["mean_send_start_to_ack_ms"] is None
    assert result["rejected_connection_timings"] == 1


def test_status_missing_spindle_fields_does_not_reuse_previous_rpm_and_diagnostics_are_separate():
    health = TransportDiagnostics()
    health.reset("c")
    health.observation("status", 1, {"state": "Idle", "spindle_rpm": 12000, "spindle_target_rpm": 12000})
    health.observation("status", 1.3, {"state": "Idle"})
    health.observation("diagnostics", 1.5, {})
    result = health.snapshot(1.6)
    assert result["status_arrivals"]["timing_source"] == "headless host monotonic receive time"
    assert result["status_arrivals"]["state"] == "incomplete"
    assert result["status_arrivals"]["latest_missing"] == ["spindle_rpm", "spindle_target_rpm"]
    assert result["status_arrivals"]["rpm_observed_minimum_change"] is None
    assert result["status_arrivals"]["arrival_age_s"] == pytest.approx(0.3)
    assert result["diagnostic_arrivals"]["arrival_age_s"] == pytest.approx(0.1)
    assert health.snapshot(4)["status_arrivals"]["state"] == "stale"
    assert result["realtime_acknowledgments_available"] is False
    with pytest.raises(ValueError, match="Unknown"):
        health.observation("other", 2, {})


def test_invalid_clock_record_is_retained_but_excluded_from_latency_summary():
    health = TransportDiagnostics()
    health.reset("c")
    bad = CommandTiming(2, 1).finish(3, "c", "controller_acknowledged")
    assert health.record_command(bad)
    assert health.record_command(timing(outcome="controller_rejected"))
    result = health.snapshot(3)
    assert result["window_commands"] == 2 and result["invalid_clock_commands"] == 1
    assert result["recent_commands"][0]["clock_issue"] == "timestamp_order"
    assert result["mean_send_start_to_ack_ms"] == pytest.approx(250)
    assert result["outcomes"]["controller_acknowledged"] == 1
    assert result["outcomes"]["controller_rejected"] == 1
