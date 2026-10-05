"""Local receipt-time playback; no interpolation, file I/O or machine transport."""

import math
from bisect import bisect_right
from dataclasses import dataclass


@dataclass(frozen=True)
class PlaybackStep:
    index: int
    recorded_at: float
    missing: bool
    running: bool
    reason: str


class ReceiptPlayback:
    """Advance a validated RecordingReplay and stop at every evidence boundary.

    A delayed UI tick may skip ordinary status events, but never a gap or
    connection boundary. The same timestamp can contain a boundary followed
    by a status packet: resuming explicitly crosses that boundary.
    """

    def __init__(self, replay):
        self.times = tuple(event["monotonic_at"] for event in replay.payload["events"])
        self.kinds = tuple(event["kind"] for event in replay.payload["events"])
        self.boundaries = tuple(i for i, kind in enumerate(self.kinds) if kind != "status")
        self.index = 0
        self.running = False
        self.speed = 1.0
        self._last_now = None

    @staticmethod
    def _number(value):
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Playback clocks must be finite nonnegative numbers")
        return value

    def play(self, index, now, speed=1.0):
        now = self._number(now)
        if type(index) is not int or not 0 <= index < len(self.times):
            raise ValueError("Choose a retained event before playback")
        if type(speed) not in (int, float) or not math.isfinite(speed) or not 0.25 <= speed <= 4:
            raise ValueError("Receipt playback speed must be between 0.25 and 4")
        self.index, self.speed = index, speed
        self._started_at = self._last_now = now
        self._recorded_start = self.times[index]
        self.running = True

    def pause(self):
        self.running = False

    def advance(self, now):
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
