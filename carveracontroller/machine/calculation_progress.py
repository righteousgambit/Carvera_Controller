"""Bounded worker progress observations, separate from calculation acceptance."""

from __future__ import annotations

import threading
from collections.abc import Callable
from time import monotonic
from typing import TypedDict


class PhaseTiming(TypedDict):
    phase: str
    elapsed_s: float


class CalculationSnapshot(TypedDict):
    phase: str
    status: str
    elapsed_s: float
    phase_elapsed_s: float
    progress_age_s: float
    processed: int
    total: int | None
    source_line: int | None
    phases: list[PhaseTiming]
    limit: str


class CalculationProgress:
    """One operation's detached observations; never schedules UI or machine work."""

    def __init__(self, phase: str, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._started = self._phase_started = self._last = clock()
        self._phase, self._status = phase, "running"
        self._processed = 0
        self._total: int | None = None
        self._line: int | None = None
        self._finished: float | None = None
        self._phases: list[PhaseTiming] = []

    def phase(self, name: str, total: int | None = None) -> None:
        with self._lock:
            if self._finished is not None:
                return
            now = self._clock()
            self._retain_phase(now)
            self._phase, self._phase_started, self._last = name, now, now
            self._processed, self._total, self._line = 0, total, None

    def advance(self, processed: int, *, source_line: int | None = None) -> None:
        with self._lock:
            if self._finished is None:
                self._processed, self._line, self._last = processed, source_line, self._clock()

    def finish(self, status: str) -> None:
        with self._lock:
            if self._finished is None:
                self._finished = self._clock()
                self._retain_phase(self._finished)
                self._status = status

    def _retain_phase(self, now: float) -> None:
        self._phases.append({"phase": self._phase, "elapsed_s": max(0, now - self._phase_started)})
        del self._phases[:-16]

    def snapshot(self) -> CalculationSnapshot:
        with self._lock:
            now = self._finished if self._finished is not None else self._clock()
            return {
                "phase": self._phase,
                "status": self._status,
                "elapsed_s": max(0, now - self._started),
                "phase_elapsed_s": max(0, now - self._phase_started),
                "progress_age_s": max(0, now - self._last),
                "processed": self._processed,
                "total": self._total,
                "source_line": self._line,
                "phases": [row.copy() for row in self._phases],
                "limit": "Desktop worker observations; timings do not prove machine execution or result acceptance",
            }


def calculation_status(snapshot: CalculationSnapshot, *, cancelling: bool = False) -> str:
    """Explain actual phase and elapsed time without inventing a completion ETA."""
    prefix = "Cancel requested · " if cancelling else ""
    count = ""
    if snapshot["total"] is not None:
        count = f" · {snapshot['processed']:,}/{snapshot['total']:,} segments"
    line = f" · line {snapshot['source_line']}" if snapshot["source_line"] is not None else ""
    return (
        f"{prefix}{snapshot['phase']}{count}{line}\n"
        f"{snapshot['elapsed_s']:.1f}s elapsed · {snapshot['phase_elapsed_s']:.1f}s in phase"
        f" · last progress {snapshot['progress_age_s']:.1f}s ago"
    )
