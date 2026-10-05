"""Shadow integration must never transmit an adaptive proposal to hardware."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample


def sample(t, **kwargs):
    return replace(Sample(t, "Idle", 12000, 12000, 0.3, 0, 100, (0, 0, 0)), **kwargs)


def calibrated():
    monitor = AdaptiveMonitor()
    monitor.capture_baseline()
    for n in range(27):
        monitor.observe(sample(n * 0.2))
    assert monitor.baseline is not None
    return monitor


def test_no_baseline_means_no_proposal_even_with_reported_cutting_droop():
    monitor = AdaptiveMonitor()
    monitor.observe(sample(1, state="Run", feed=600, rpm=11850))
    assert monitor.proposed == 100
    assert monitor.baseline is None


@pytest.mark.parametrize("bad", [{"feed": 1}, {"state": "Run"}, {"rpm": 0}, {"rpm": 5000}])
def test_baseline_refuses_moving_or_stopped_or_spinning_up_samples(bad):
    monitor = AdaptiveMonitor()
    monitor.capture_baseline()
    for n in range(40):
        monitor.observe(sample(n * 0.2, **bad))
    assert monitor.baseline is None


def test_baseline_refuses_position_motion_even_if_feed_field_says_zero():
    monitor = AdaptiveMonitor()
    monitor.capture_baseline()
    for n in range(40):
        monitor.observe(sample(n * 0.2, position=(n, 0, 0)))
    assert monitor.baseline is None


def test_rpm_droop_in_reported_engagement_range_proposes_bounded_backoff():
    monitor = calibrated()
    for n in range(1, 100):
        monitor.observe(sample(5.2 + n * 0.2, state="Run", feed=600, rpm=11850))
    assert monitor.proposed == 40
    assert "floor" in monitor.reason


def test_feed_recovery_is_slow_and_capped_at_programmed_ceiling():
    monitor = calibrated()
    monitor.proposed = 80
    for n in range(1, 8):
        monitor.observe(sample(5.2 + n * 0.2, state="Run", feed=600))
    assert monitor.proposed == 80
    for n in range(8, 150):
        monitor.observe(sample(5.2 + n * 0.2, state="Run", feed=600))
    assert 80 < monitor.proposed <= 100


def test_missing_pwm_is_unknown_and_does_not_reuse_previous_effort():
    monitor = calibrated()
    monitor.observe(sample(5.4, state="Run", feed=600, pwm=None))
    assert monitor.snapshot()["sample"]["pwm"] is None


def test_speed_change_invalidates_baseline():
    monitor = calibrated()
    monitor.observe(sample(5.4, commanded_rpm=10000, rpm=10000))
    assert monitor.baseline is None


def test_stale_telemetry_is_explicit_and_never_a_recovery_signal():
    monitor = calibrated()
    monitor.proposed = 60
    monitor.tick(10)
    assert "stale" in monitor.reason
    assert monitor.proposed == 60


def test_fault_does_not_automatically_clear_when_speed_recovers():
    monitor = calibrated()
    monitor.observe(sample(5.4, state="Run", feed=600, rpm=10000))
    assert "severe" in monitor.reason
    monitor.observe(sample(5.6, state="Run", feed=600, rpm=12000))
    assert "severe" in monitor.reason
    assert "severe" in monitor.snapshot()["fault"]
    monitor.capture_baseline()
    assert monitor.fault is None
    assert monitor.snapshot()["fault"] is None


@pytest.mark.parametrize("bad", [{"rpm": float("nan")}, {"pwm": float("inf")}, {"pwm": 2}, {"feed": -1}])
def test_invalid_values_invalidate_baseline(bad):
    monitor = calibrated()
    monitor.observe(sample(5.4, **bad))
    assert monitor.baseline is None
    assert "invalid" in monitor.reason


def test_local_commands_cannot_reach_transport():
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    for command in ("adaptive status", "adaptive baseline", "adaptive active", "adaptive shadow", "adaptive off"):
        controller.executeCommand(command)
    controller.stream.send.assert_not_called()
    assert not controller.adaptive_monitor.enabled


def test_status_packet_records_shadow_telemetry_without_transmitting(tmp_path, monkeypatch):
    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller.parseBracketAngle(
        "<Idle|MPos:-232,-195.285,-3|WPos:-232,-195.285,-53.480|S:0,12000,100,0,35|F:0,600,100|PWM:0>"
    )
    assert controller._adaptive_log.drain()["written"] == 1
    assert controller.adaptive_log_path.exists()
    assert controller.adaptive_monitor.last.rpm == 0
    controller.parseBracketAngle(
        "<Idle|MPos:-232,-195.285,-3|WPos:-232,-195.285,-53.480|S:0,12000,100,0,35|F:0,600,100>"
    )
    assert not CNC.vars["has_spindle_pwm"]
    assert controller.adaptive_monitor.last.pwm is None
    controller._connection_generation += 1
    controller.parseBracketAngle(
        "<Idle|MPos:-232,-195.285,-3|WPos:-232,-195.285,-53.480|S:0,12000,100,0,35|F:0,600,100>"
    )
    receipt = controller.stop_telemetry_logging()
    assert receipt["drained"] and receipt["written"] == 3
    records = [json.loads(line) for line in controller.adaptive_log_path.read_text().splitlines()]
    assert records[0]["connection_generation"] + 1 == records[-1]["connection_generation"]
    assert records[-1]["persistence"]["sequence"] == 3
    controller.stream.send.assert_not_called()


def test_partial_status_updates_quality_without_refreshing_complete_spindle_sample(tmp_path, monkeypatch):
    import json

    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller._observe_adaptive({"S": [12000, 12000, 100], "F": [0, 600, 100], "MPos": [0, 0, 0]})
    previous = controller.adaptive_monitor.last
    controller._observe_adaptive({"MPos": [0, 0, 0]})
    quality = controller.adaptive_monitor.quality.snapshot()
    assert quality["window_packets"] == 2 and quality["complete_packets"] == 1
    assert quality["latest_missing"] == ["S", "F"]
    assert controller.adaptive_monitor.last is previous
    assert controller._adaptive_log.drain()["written"] == 2
    records = [json.loads(line) for line in controller.adaptive_log_path.read_text().splitlines()]
    assert len(records) == 2 and records[-1]["packet_complete"] is False
    assert records[-1]["telemetry_quality"]["latest_missing"] == ["S", "F"]
    assert records[-1]["sample"]["timestamp"] == previous.timestamp
    controller.stream.send.assert_not_called()
    controller.adaptive_monitor.reset()
    assert controller.adaptive_monitor.quality.snapshot()["window_packets"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"timestamp": "5.4"},
        {"timestamp": True},
        {"timestamp": -1},
        {"timestamp": 1e308},
        {"timestamp": 10**1000},
        {"rpm": "12000"},
        {"rpm": True},
        {"rpm": 10**1000},
        {"pwm": "0.3"},
        {"pwm": False},
        {"feed": None},
        {"override": "100"},
        {"position": None},
        {"position": (0, 0)},
        {"position": (0, 0, 0, 0)},
        {"position": (0, True, 0)},
        {"position": (0, "0", 0)},
        {"state": None},
        {"state": " "},
    ],
)
def test_malformed_runtime_sample_latches_fault_without_replacing_last_good_sample(bad):
    monitor = calibrated()
    previous = monitor.last
    count = len(monitor.history)
    result = monitor.observe(sample(5.4, **bad))
    assert result["fault"].startswith("invalid telemetry")
    assert result["baseline"] is None
    assert monitor.last is previous and len(monitor.history) == count
    assert result["active_control_available"] is False
    # A rejected signal must still produce a JSON-safe diagnostic export.
    json.dumps(monitor.quality.export(5.5), allow_nan=False)


@pytest.mark.parametrize("now", [float("nan"), float("inf"), "5.4", True, -1, 1e308, 10**1000, 4])
def test_bad_monitor_clock_latches_and_cannot_trigger_recovery(now):
    monitor = calibrated()
    monitor.proposed = 60
    monitor.tick(now)
    assert "clock" in monitor.fault
    assert monitor.proposed == 60
    monitor.observe(sample(5.4, state="Run", feed=600))
    assert "clock" in monitor.fault


def test_capture_progress_restarts_on_motion_and_snapshot_cannot_modify_baseline():
    monitor = AdaptiveMonitor()
    monitor.capture_baseline()
    for n in range(12):
        monitor.observe(sample(n * 0.2))
    progress = monitor.snapshot()["baseline_capture"]
    assert progress == {"active": True, "elapsed_s": 2.2, "required_s": 5, "samples": 12}
    monitor.observe(sample(2.4, feed=1))
    assert monitor.snapshot()["baseline_capture"]["elapsed_s"] == 0
    assert monitor.snapshot()["baseline_capture"]["samples"] == 0
    for n in range(28):
        monitor.observe(sample(2.6 + n * 0.2))
    result = monitor.snapshot()
    assert result["baseline_capture"]["active"] is False
    result["baseline"]["rpm"] = 1
    assert monitor.baseline["rpm"] == 12000


def test_explicit_recapture_after_stale_fault_requires_a_whole_new_baseline():
    monitor = calibrated()
    monitor.tick(10)
    retained = len(monitor.history)
    monitor.capture_baseline()
    assert monitor.snapshot()["sample"] is None
    assert len(monitor.history) == retained
    for n in range(27):
        result = monitor.observe(sample(10.2 + n * 0.2))
        if n < 25:
            assert result["baseline"] is None
    assert result["fault"] is None
    assert result["baseline"]["samples"] >= 26
    assert monitor.quality.snapshot()["gap_count"] == 1
