"""Tests for adaptive feed override suggestions.

This is the feature most able to break a tool, so the tests are about what
it refuses to do at least as much as what it does.
"""

import pytest

from carveracontroller.machine.adaptive_feed import (
    AdaptiveFeedConfig,
    suggest_override,
)
from carveracontroller.machine.spindle import SpindleLoad, SpindleLoadState

_ON = AdaptiveFeedConfig(enabled=True)


def _load(effort, state=SpindleLoadState.NORMAL, droop=0.0):
    return SpindleLoad(state, effort, droop)


# ------------------------------------------------------------- refusals


def test_disabled_by_default():
    """Adaptive control is opt-in, not a default behaviour."""
    result = suggest_override(_load(0.20), 100.0, AdaptiveFeedConfig())

    assert not result.changed
    assert "off" in result.reason


def test_unknown_load_does_nothing():
    """Absent PWM must never be read as no load and used to speed up."""
    unknown = SpindleLoad(SpindleLoadState.UNKNOWN, 0.0, 0.0)
    result = suggest_override(unknown, 100.0, _ON)

    assert not result.changed
    assert "not reported" in result.reason


def test_idle_spindle_does_nothing():
    idle = SpindleLoad(SpindleLoadState.IDLE, 0.0, 0.0)
    assert not suggest_override(idle, 80.0, _ON).changed


# ------------------------------------------------------------- backing off


def test_high_load_backs_off():
    result = suggest_override(_load(0.85, SpindleLoadState.HIGH), 100.0, _ON)

    assert result.changed
    assert result.override == pytest.approx(90.0)


def test_saturation_backs_off_whatever_effort_reads():
    """Droop means headroom is already gone, even if PWM dipped this tick."""
    saturated = SpindleLoad(SpindleLoadState.SATURATED, 0.20, droop=0.15)
    result = suggest_override(saturated, 100.0, _ON)

    assert result.changed
    assert result.override == pytest.approx(90.0)


def test_backoff_stops_at_the_floor():
    result = suggest_override(_load(0.95, SpindleLoadState.HIGH), 45.0, _ON)
    assert result.override == pytest.approx(40.0)


def test_at_the_floor_it_stops_rather_than_creeping_to_zero():
    """An adaptive controller that can stall the feed will rub and glaze."""
    result = suggest_override(_load(0.99, SpindleLoadState.SATURATED), 40.0, _ON)

    assert not result.changed
    assert result.override == pytest.approx(40.0)
    assert "minimum" in result.reason


# -------------------------------------------------------------- recovering


def test_low_load_recovers_slowly():
    result = suggest_override(_load(0.30), 80.0, _ON)

    assert result.changed
    assert result.override == pytest.approx(82.0)


def test_recovery_is_slower_than_backoff():
    """Overload is urgent; being slightly slow is not."""
    up = suggest_override(_load(0.10), 80.0, _ON).override - 80.0
    down = 80.0 - suggest_override(_load(0.90, SpindleLoadState.HIGH), 80.0, _ON).override

    assert down > up


def test_recovery_stops_at_the_ceiling():
    result = suggest_override(_load(0.10), 100.0, _ON)

    assert not result.changed
    assert "maximum" in result.reason


def test_never_speeds_up_while_load_is_high():
    for effort in (0.76, 0.85, 0.99):
        result = suggest_override(_load(effort, SpindleLoadState.HIGH), 70.0, _ON)
        assert result.override <= 70.0, f"sped up at effort {effort}"


# ------------------------------------------------------------------- band


def test_inside_the_target_band_nothing_changes():
    for effort in (0.55, 0.65, 0.75):
        result = suggest_override(_load(effort), 90.0, _ON)
        assert not result.changed, f"adjusted inside the band at {effort}"


def test_the_band_settles_rather_than_oscillating():
    """Walk the controller from overload and check it lands in the band."""
    override = 100.0
    for _ in range(20):
        # Effort falls as override falls, crudely but monotonically.
        effort = 0.95 * (override / 100.0)
        state = SpindleLoadState.HIGH if effort > 0.75 else SpindleLoadState.NORMAL
        override = suggest_override(_load(effort, state), override, _ON).override

    final_effort = 0.95 * (override / 100.0)
    assert _ON.target_low <= final_effort <= _ON.target_high


# ---------------------------------------------------------------- config


@pytest.mark.parametrize(
    "bad",
    [
        AdaptiveFeedConfig(enabled=True, target_low=0.8, target_high=0.6),
        AdaptiveFeedConfig(enabled=True, target_low=0.0, target_high=0.6),
        AdaptiveFeedConfig(enabled=True, target_high=1.5),
        AdaptiveFeedConfig(enabled=True, min_override=0.0),
        AdaptiveFeedConfig(enabled=True, min_override=90.0, max_override=50.0),
        AdaptiveFeedConfig(enabled=True, backoff_step=0.0),
        AdaptiveFeedConfig(enabled=True, recover_step=-1.0),
    ],
)
def test_nonsense_configuration_is_rejected(bad):
    with pytest.raises(ValueError):
        suggest_override(_load(0.5), 100.0, bad)
