"""Accumulated machine usage, for service intervals and tool life.

Counters advance from observed state rather than from a running total the
machine reports, because the machine does not report one. Spindle time
accumulates while the spindle is turning; tool changes and probe cycles count
transitions. Feed it status updates and it keeps the tally.

Kivy-free by contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

COUNTERS_FORMAT_VERSION = 1

# Gaps longer than this are treated as the app being asleep rather than the
# spindle running, so a closed laptop does not book hours of runtime.
MAX_CREDITED_INTERVAL_SECONDS = 30.0


@dataclass
class UsageCounters:
    spindle_seconds: float = 0.0
    tool_changes: int = 0
    probe_cycles: int = 0
    jobs_started: int = 0
    jobs_completed: int = 0

    _last_timestamp: float | None = field(default=None, repr=False)
    _last_tool: int | None = field(default=None, repr=False)
    _spindle_was_on: bool = field(default=False, repr=False)

    @property
    def spindle_hours(self) -> float:
        return self.spindle_seconds / 3600.0

    def observe(self, timestamp: float, spindle_rpm: float, tool: int | None = None) -> None:
        """Advance counters from one status observation.

        Credits elapsed time to the spindle only when it was already turning
        at the previous observation, so a single sample never books time
        retrospectively.
        """
        previous_time = self._last_timestamp
        spindle_was_on = self._spindle_was_on
        self._last_timestamp = timestamp
        self._spindle_was_on = spindle_rpm > 0

        # The interval belongs to the state at its start. Crediting it on the
        # strength of the current reading books the idle time before spin-up.
        if previous_time is not None and spindle_was_on:
            elapsed = timestamp - previous_time
            if 0 < elapsed <= MAX_CREDITED_INTERVAL_SECONDS:
                self.spindle_seconds += elapsed

        if tool is not None:
            if self._last_tool is not None and tool != self._last_tool:
                self.tool_changes += 1
            self._last_tool = tool

    def count_probe_cycle(self) -> None:
        self.probe_cycles += 1

    def start_job(self) -> None:
        self.jobs_started += 1

    def complete_job(self) -> None:
        self.jobs_completed += 1

    def reset_session(self) -> None:
        """Forget the last observation without discarding totals.

        Called on disconnect, so the gap across a disconnection is not
        credited as runtime when the machine comes back.
        """
        self._last_timestamp = None
        self._last_tool = None
        self._spindle_was_on = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": COUNTERS_FORMAT_VERSION,
            "spindle_seconds": self.spindle_seconds,
            "tool_changes": self.tool_changes,
            "probe_cycles": self.probe_cycles,
            "jobs_started": self.jobs_started,
            "jobs_completed": self.jobs_completed,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_json(text: str) -> UsageCounters:
        if not text.strip():
            return UsageCounters()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return UsageCounters()
            return UsageCounters(
                spindle_seconds=float(data.get("spindle_seconds", 0.0)),
                tool_changes=int(data.get("tool_changes", 0)),
                probe_cycles=int(data.get("probe_cycles", 0)),
                jobs_started=int(data.get("jobs_started", 0)),
                jobs_completed=int(data.get("jobs_completed", 0)),
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            return UsageCounters()


@dataclass(frozen=True)
class ServiceInterval:
    name: str
    every_hours: float
    task: str

    def due_in(self, counters: UsageCounters) -> float:
        """Spindle hours until due. Negative when overdue."""
        if self.every_hours <= 0:
            return 0.0
        hours = counters.spindle_hours
        elapsed_in_period = hours % self.every_hours
        # Landing exactly on a multiple means due now, not a fresh period.
        if hours > 0 and elapsed_in_period == 0:
            return 0.0
        return self.every_hours - elapsed_in_period

    def is_due(self, counters: UsageCounters, warn_within_hours: float = 1.0) -> bool:
        return self.due_in(counters) <= warn_within_hours


DEFAULT_SERVICE_INTERVALS = (
    ServiceInterval("Chip clearance", 8.0, "Clear chips from the rails, ballscrews and tool changer."),
    ServiceInterval("Lubrication", 40.0, "Check and apply lubricant to the linear rails and ballscrews."),
    ServiceInterval("Spindle check", 100.0, "Check spindle runout and listen for bearing noise."),
    ServiceInterval("Collet inspection", 40.0, "Inspect collets for wear, debris and damage."),
)
