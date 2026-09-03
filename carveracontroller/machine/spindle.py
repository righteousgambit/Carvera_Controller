"""Spindle load interpretation.

The firmware holds commanded RPM with a closed integrating loop, raising PWM
effort as cutting load increases. Speed therefore stays flat while effort
climbs, and only falls once effort saturates. That makes PWM the proportional
load signal and RPM droop a late, near-binary one — a distinction the UI has
to get right or it will report "fine" until the moment it reports "stalling".

Kivy-free by contract so it can be reasoned about and tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Effort above which the spindle is working hard but still has headroom.
HIGH_EFFORT_THRESHOLD = 0.75
# Effort at which there is effectively no headroom left. Below 1.0 because the
# loop oscillates slightly around saturation.
SATURATED_EFFORT_THRESHOLD = 0.95
# Speed loss that counts as real droop rather than loop noise.
DROOP_THRESHOLD = 0.02


class SpindleLoadState(Enum):
    """How close the spindle is to running out of headroom."""

    UNKNOWN = "unknown"
    """No PWM field in the status report — stock firmware, or not yet polled."""

    IDLE = "idle"
    NORMAL = "normal"
    HIGH = "high"
    SATURATED = "saturated"


@dataclass(frozen=True)
class SpindleLoad:
    state: SpindleLoadState
    effort: float
    """PWM effort, 0.0-1.0. Zero when unknown."""

    droop: float
    """Fraction below commanded speed, 0.0-1.0."""

    @property
    def is_known(self) -> bool:
        return self.state is not SpindleLoadState.UNKNOWN

    @property
    def needs_attention(self) -> bool:
        return self.state in (SpindleLoadState.HIGH, SpindleLoadState.SATURATED)


def spindle_droop(current_rpm: float, target_rpm: float, override_percent: float = 100.0) -> float:
    """Fraction by which actual speed sits below the commanded speed."""
    commanded = target_rpm * (override_percent / 100.0)
    if commanded <= 0.0:
        return 0.0
    return max(0.0, (commanded - current_rpm) / commanded)


def evaluate_spindle_load(
    current_rpm: float,
    target_rpm: float,
    pwm: float | None,
    override_percent: float = 100.0,
) -> SpindleLoad:
    """Classify spindle load.

    ``pwm`` is ``None`` when the machine did not report a ``PWM:`` field, which
    is the case on stock firmware. That is reported as ``UNKNOWN`` rather than
    as zero load: absent data must not render as "no load".
    """
    droop = spindle_droop(current_rpm, target_rpm, override_percent)

    if pwm is None:
        return SpindleLoad(SpindleLoadState.UNKNOWN, 0.0, droop)

    effort = min(1.0, max(0.0, pwm))

    if target_rpm <= 0.0 and current_rpm <= 0.0:
        return SpindleLoad(SpindleLoadState.IDLE, effort, 0.0)

    # Real droop means the loop has already run out of headroom, whatever the
    # instantaneous effort reads.
    if effort >= SATURATED_EFFORT_THRESHOLD or droop >= DROOP_THRESHOLD:
        return SpindleLoad(SpindleLoadState.SATURATED, effort, droop)
    if effort >= HIGH_EFFORT_THRESHOLD:
        return SpindleLoad(SpindleLoadState.HIGH, effort, droop)
    return SpindleLoad(SpindleLoadState.NORMAL, effort, droop)
