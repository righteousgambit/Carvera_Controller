"""Feed override suggestions from measured spindle load.

Back off when the spindle is working too hard, recover when it is not. The
principle is simple; the danger is that a controller which reacts wrongly
breaks a tool or a part, so the behaviour here is deliberately timid.

Design rules, in order of importance:

* Never speeds up while load is above the target band. Recovery only happens
  from below.
* Backs off faster than it recovers. Overload is urgent; being slightly slow
  is not.
* Refuses to act on load it does not have. Unknown reads as "do nothing",
  never as "no load".
* Has a hard floor, so it cannot creep the feed toward zero and dwell in the
  cut.
* Deadband inside the target band, so it settles rather than oscillating.

This computes a suggestion. Nothing here sends anything to a machine.

Kivy-free by contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from .spindle import SpindleLoad, SpindleLoadState

# Load band to aim for, as PWM effort. Below this there is headroom going
# unused; above it, the spindle has little left before it saturates.
DEFAULT_TARGET_LOW = 0.55
DEFAULT_TARGET_HIGH = 0.75

# Override bounds, in percent. The floor is well above zero: an adaptive
# controller that can stall the feed will rub, overheat and glaze the cut.
DEFAULT_MIN_OVERRIDE = 40.0
DEFAULT_MAX_OVERRIDE = 100.0

# Percent per adjustment. Asymmetric on purpose.
DEFAULT_BACKOFF_STEP = 10.0
DEFAULT_RECOVER_STEP = 2.0


@dataclass(frozen=True)
class AdaptiveFeedConfig:
    enabled: bool = False
    """Off unless deliberately turned on. This is not a default behaviour."""

    target_low: float = DEFAULT_TARGET_LOW
    target_high: float = DEFAULT_TARGET_HIGH
    min_override: float = DEFAULT_MIN_OVERRIDE
    max_override: float = DEFAULT_MAX_OVERRIDE
    backoff_step: float = DEFAULT_BACKOFF_STEP
    recover_step: float = DEFAULT_RECOVER_STEP

    def validate(self) -> None:
        if not 0.0 < self.target_low < self.target_high < 1.0:
            raise ValueError("target band must satisfy 0 < low < high < 1")
        if not 0.0 < self.min_override <= self.max_override:
            raise ValueError("override bounds must satisfy 0 < min <= max")
        if self.backoff_step <= 0 or self.recover_step <= 0:
            raise ValueError("steps must be positive")


@dataclass(frozen=True)
class FeedAdjustment:
    override: float
    """The override to apply, in percent. Unchanged when no action is due."""

    changed: bool
    reason: str

    @property
    def is_backoff(self) -> bool:
        return self.changed and "load" in self.reason and "high" in self.reason


def suggest_override(
    load: SpindleLoad,
    current_override: float,
    config: AdaptiveFeedConfig | None = None,
) -> FeedAdjustment:
    """Suggest a feed override for the current spindle load."""
    config = config or AdaptiveFeedConfig()
    config.validate()

    if not config.enabled:
        return FeedAdjustment(current_override, False, "adaptive feed is off")

    if not load.is_known:
        return FeedAdjustment(current_override, False, "spindle load is not reported")

    if load.state is SpindleLoadState.IDLE:
        return FeedAdjustment(current_override, False, "spindle is not cutting")

    # Saturation means the loop has already run out of headroom. Back off by a
    # full step regardless of where effort happens to read this instant.
    if load.state is SpindleLoadState.SATURATED:
        return _step_down(current_override, config, "spindle saturated, load too high")

    if load.effort > config.target_high:
        return _step_down(current_override, config, "load too high")

    if load.effort < config.target_low:
        return _step_up(current_override, config, "load below target")

    return FeedAdjustment(current_override, False, "load within target band")


def _step_down(current: float, config: AdaptiveFeedConfig, reason: str) -> FeedAdjustment:
    target = max(config.min_override, current - config.backoff_step)
    if target >= current:
        return FeedAdjustment(current, False, f"{reason}, already at minimum override")
    return FeedAdjustment(target, True, reason)


def _step_up(current: float, config: AdaptiveFeedConfig, reason: str) -> FeedAdjustment:
    target = min(config.max_override, current + config.recover_step)
    if target <= current:
        return FeedAdjustment(current, False, f"{reason}, already at maximum override")
    return FeedAdjustment(target, True, reason)
