"""Tests for spindle load interpretation."""

import pytest

from carveracontroller.machine.spindle import (
    SpindleLoadState,
    evaluate_spindle_load,
    spindle_droop,
)


def test_absent_pwm_is_unknown_not_zero_load():
    """Stock firmware omits the field; that must not render as 'no load'."""
    load = evaluate_spindle_load(current_rpm=12000, target_rpm=12000, pwm=None)

    assert load.state is SpindleLoadState.UNKNOWN
    assert not load.is_known
    assert not load.needs_attention


def test_stopped_spindle_is_idle():
    load = evaluate_spindle_load(current_rpm=0.0, target_rpm=0.0, pwm=0.0)
    assert load.state is SpindleLoadState.IDLE


@pytest.mark.parametrize(
    ("pwm", "expected"),
    [
        (0.30, SpindleLoadState.NORMAL),
        (0.74, SpindleLoadState.NORMAL),
        (0.75, SpindleLoadState.HIGH),
        (0.94, SpindleLoadState.HIGH),
        (0.95, SpindleLoadState.SATURATED),
        (1.00, SpindleLoadState.SATURATED),
    ],
)
def test_effort_thresholds(pwm, expected):
    load = evaluate_spindle_load(current_rpm=14000, target_rpm=14000, pwm=pwm)
    assert load.state is expected


def test_droop_forces_saturated_even_when_effort_reads_low():
    """Speed already lost means headroom is gone, whatever PWM says this tick."""
    load = evaluate_spindle_load(current_rpm=11000, target_rpm=14000, pwm=0.20)

    assert load.state is SpindleLoadState.SATURATED
    assert load.droop == pytest.approx(3000 / 14000)


def test_effort_is_clamped():
    assert evaluate_spindle_load(14000, 14000, pwm=1.4).effort == pytest.approx(1.0)
    assert evaluate_spindle_load(14000, 14000, pwm=-0.2).effort == pytest.approx(0.0)


def test_droop_accounts_for_override():
    """At 50 % override the commanded speed halves, so 7000 is on target."""
    assert spindle_droop(7000, 14000, override_percent=50.0) == pytest.approx(0.0)
    assert spindle_droop(14000, 14000, override_percent=50.0) == pytest.approx(0.0)
    assert spindle_droop(3500, 14000, override_percent=50.0) == pytest.approx(0.5)


def test_no_droop_reported_when_spindle_is_off():
    assert spindle_droop(0.0, 0.0) == 0.0


def test_high_effort_flags_attention_before_speed_moves():
    """The whole point: warn while RPM still looks perfect."""
    load = evaluate_spindle_load(current_rpm=14000, target_rpm=14000, pwm=0.88)

    assert load.droop == pytest.approx(0.0)
    assert load.needs_attention
