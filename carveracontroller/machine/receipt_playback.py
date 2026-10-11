"""Local receipt-time playback; no interpolation, file I/O or machine transport."""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

from carveracontroller.machine.run_recording import RecordingReplay


@dataclass(frozen=True)
class PlaybackStep:
    index: int
    recorded_at: float
    missing: bool
    running: bool
    reason: str


@dataclass(frozen=True)
class ReceiptPosition:
    elapsed_seconds: float
    duration_seconds: float
    next_boundary_index: int | None
    next_boundary_elapsed_seconds: float | None
    next_boundary_reason: str | None


class ReceiptPlayback:
    """Advance a validated RecordingReplay and stop at every evidence boundary.

    A delayed UI tick may skip ordinary status events, but never a gap or
    connection boundary. The same timestamp can contain a boundary followed
    by a status packet: resuming explicitly crosses that boundary.
    """

    def __init__(self, replay: RecordingReplay) -> None:
        self.times = tuple(event["monotonic_at"] for event in replay.payload["events"])
        self.kinds = tuple(event["kind"] for event in replay.payload["events"])
        self.boundaries = tuple(i for i, kind in enumerate(self.kinds) if kind != "status")
        self.index = 0
        self.running = False
        self.speed = 1.0
        self._last_now: float | None = None
        self._started_at = 0.0
        self._recorded_start = 0.0

    @staticmethod
    def _number(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Playback clocks must be finite nonnegative numbers")
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError("Playback clocks must be finite nonnegative numbers") from exc
        if not math.isfinite(number) or number < 0:
            raise ValueError("Playback clocks must be finite nonnegative numbers")
        return number

    def position(self, index: int, recorded_at: float | None = None) -> ReceiptPosition:
        """Receipt-relative time and next evidence boundary, without packet scans."""
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(self.times):
            raise ValueError("Choose a retained event before playback")
        stamp = self.times[index] if recorded_at is None else self._number(recorded_at)
        if not self.times[0] <= stamp <= self.times[-1]:
            raise ValueError("Receipt position is outside the retained interval")
        slot = bisect_right(self.boundaries, index)
        boundary = self.boundaries[slot] if slot < len(self.boundaries) else None
        return ReceiptPosition(
            stamp - self.times[0],
            self.times[-1] - self.times[0],
            boundary,
            None if boundary is None else self.times[boundary] - self.times[0],
            None if boundary is None else self.kinds[boundary],
        )

    def play(self, index: int, now: object, speed: object = 1.0) -> None:
        now = self._number(now)
        if type(index) is not int or not 0 <= index < len(self.times):
            raise ValueError("Choose a retained event before playback")
        try:
            rate = self._number(speed)
        except ValueError as exc:
            raise ValueError("Receipt playback speed must be between 0.25 and 4") from exc
        if not 0.25 <= rate <= 4:
            raise ValueError("Receipt playback speed must be between 0.25 and 4")
        self.index, self.speed = index, rate
        self._started_at = self._last_now = now
        self._recorded_start = self.times[index]
        self.running = True

    def pause(self) -> None:
        self.running = False

    def advance(self, now: object) -> PlaybackStep:
        now = self._number(now)
        if self._last_now is not None and now < self._last_now:
            self.pause()
            raise ValueError("Playback clock moved backwards")
        if not self.running:
            raise ValueError("Receipt playback is paused")
        self._last_now = now
        target = min(self.times[-1], self._recorded_start + (now - self._started_at) * self.speed)
        candidate = max(self.index, bisect_right(self.times, target) - 1)
        boundary_slot = bisect_right(self.boundaries, self.index)
        boundary = self.boundaries[boundary_slot] if boundary_slot < len(self.boundaries) else None
        if boundary is not None and boundary <= candidate:
            self.index = boundary
            self.pause()
            return PlaybackStep(boundary, self.times[boundary], True, False, self.kinds[boundary])
        self.index = candidate
        following = candidate + 1
        missing = following < len(self.times) and self.kinds[following] != "status" and target > self.times[candidate]
        if candidate == len(self.times) - 1:
            self.pause()
        return PlaybackStep(candidate, target, missing, self.running, "missing_interval" if missing else "status")
