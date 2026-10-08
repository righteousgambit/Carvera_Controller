"""Decision evidence must follow the real policy and never imply executed control."""

from dataclasses import replace

import pytest

from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample


def sample(t, **changes):
    return replace(Sample(t, "Idle", 12000, 12000, 0.3, 0, 100, (0, 0, 0)), **changes)


def calibrated():
    monitor = AdaptiveMonitor()
    monitor.capture_baseline()
    for n in range(27):
        monitor.observe(sample(n * 0.2))
    assert monitor.baseline
    return monitor


def cutting(monitor, t, **changes):
    return monitor.observe(sample(t, state="Run", feed=600, **changes))["decision"]


@pytest.mark.parametrize(
    "rpm,pwm,factor,status",
    [
        (11600, None, "Filtered baseline RPM droop", "backoff"),
        (12000, 0.96, "Drive effort", "backoff"),
        (11600, 0.96, "Filtered baseline RPM droop and drive effort", "backoff"),
        (12000, None, "100% programmed-feed ceiling", "ceiling"),
        (12000, 0.8, "Experimental load band", "retain"),
    ],
)
def test_governing_factor_matches_policy(rpm, pwm, factor, status):
    monitor = calibrated()
    decision = cutting(monitor, 5.4, rpm=rpm, pwm=pwm)
    assert decision["limiting_factor"] == factor
    assert decision["status"] == status
    assert decision["proposal_percent"] == monitor.proposed
    assert decision["pwm"] == pwm
    assert decision["raw_droop"] == pytest.approx((12000 - rpm) / 12000)
    assert decision["program_line"] is None


def test_floor_and_recovery_dwell_have_exact_bounds_and_read_only_snapshot():
    monitor = calibrated()
    monitor.proposed = 45
    decision = cutting(monitor, 5.4, pwm=0.96)
    assert decision["status"] == "would hold"
    assert decision["proposal_percent"] == 40
    assert decision["limiting_factor"] == "40% experimental feed floor"
    assert decision["next_adjustment_s"] == pytest.approx(0.4)
    monitor.proposed = 80
    decision = cutting(monitor, 5.6, pwm=None)
    assert decision["status"] == "recovery"
    assert decision["next_adjustment_s"] == pytest.approx(1.8)
    before = (monitor.proposed, monitor.filtered_droop, monitor.last_adjustment, tuple(monitor.history))
    monitor.snapshot(5.7)
    assert before == (monitor.proposed, monitor.filtered_droop, monitor.last_adjustment, tuple(monitor.history))


@pytest.mark.parametrize("case", ["stale", "future", "fault", "off", "no_baseline", "idle", "capture"])
def test_ineligible_states_never_show_proposals_or_response(case):
    monitor = calibrated()
    cutting(monitor, 5.4, override=100)
    cutting(monitor, 5.6, override=80)
    now = 5.6
    if case == "stale":
        now = 6.401
    elif case == "future":
        now = 5.5
    elif case == "fault":
        monitor.fault = "latched fault"
    elif case == "off":
        monitor.enabled = False
    elif case == "no_baseline":
        monitor.baseline = None
    elif case == "idle":
        monitor.observe(sample(5.8))
        now = 5.8
    else:
        monitor.capture_baseline()
    decision = monitor.snapshot(now)["decision"]
    assert decision["proposal_percent"] is None
    assert decision["response"]["rpm_change"] is None
    assert decision["response"]["status"] == "unavailable"


def test_response_is_reported_override_association_not_shadow_execution():
    monitor = calibrated()
    cutting(monitor, 5.4, rpm=11800, override=100)
    first = cutting(monitor, 5.6, rpm=11900, override=80, position=(1, 2, 3))
    assert first["response"]["status"] == "collecting"
    for n in range(1, 7):
        decision = cutting(monitor, 5.6 + n * 0.2, rpm=11950, override=80, position=(n, 2, 3))
    response = decision["response"]
    assert response["status"] == "observed"
    assert response["override_before"] == 100 and response["override_after"] == 80
    assert response["rpm_change"] == 150
    assert response["arrival_time"] == 5.6
    assert response["elapsed_s"] == pytest.approx(1.2)
    assert "does not establish a causal response" in response["explanation"]
    assert decision["machine_position"] == (6, 2, 3)
    assert decision["program_line"] is None
    assert first["response"]["rpm_after"] == 11900  # Exported snapshots retain their own evidence.


@pytest.mark.parametrize("interrupt", ["idle", "zero_feed", "speed", "gap", "reverse_time", "old"])
def test_response_does_not_cross_a_signal_or_motion_boundary(interrupt):
    monitor = calibrated()
    cutting(monitor, 5.4, rpm=11800)
    cutting(monitor, 5.6, rpm=11900, override=80)
    if interrupt == "idle":
        monitor.observe(sample(5.8, override=80))
    elif interrupt == "zero_feed":
        monitor.observe(sample(5.8, state="Run", feed=0, override=80))
    elif interrupt == "speed":
        monitor.observe(sample(5.8, state="Run", feed=600, commanded_rpm=10000, rpm=10000, override=80))
    elif interrupt in ("gap", "reverse_time"):
        cutting(monitor, 6.6 if interrupt == "gap" else 5.5, override=80)
    else:
        for n in range(1, 28):
            cutting(monitor, 5.6 + n * 0.2, override=80)
    decision = cutting(monitor, monitor.last.timestamp + 0.2, override=80)
    assert decision["response"]["status"] == "unavailable"


def test_latest_override_change_wins_and_severe_droop_remains_latched():
    monitor = calibrated()
    cutting(monitor, 5.4, rpm=11800)
    cutting(monitor, 5.6, rpm=11900, override=80)
    decision = cutting(monitor, 5.8, rpm=11950, override=70)
    assert decision["response"]["override_before"] == 80
    assert decision["response"]["rpm_change"] == 50
    severe = cutting(monitor, 6.0, rpm=11000, override=70)
    assert severe["status"] == "blocked" and severe["proposal_percent"] is None
    recovered = cutting(monitor, 6.2, override=70)
    assert recovered["limiting_factor"] == "Latched monitor fault"


def test_controller_recording_contains_decision_context_without_transport(tmp_path, monkeypatch):
    import json
    from unittest.mock import Mock

    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    monkeypatch.setitem(CNC.vars, "state", "Run")
    controller._observe_adaptive({"S": [12000, 12000, 100], "F": [600, 600, 80], "MPos": [1, 2, 3]})
    assert controller.stop_telemetry_logging()["drained"]
    record = json.loads(controller.adaptive_log_path.read_text().splitlines()[-1])
    assert record["decision"]["machine_position"] == [1, 2, 3]
    assert record["decision"]["program_line"] is None
    assert record["decision"]["proposal_percent"] is None
    controller.stream.send.assert_not_called()
