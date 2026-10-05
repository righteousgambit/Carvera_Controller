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
    monitor.capture_baseline()
    assert monitor.fault is None


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
