"""Connection-bound G28.6 receipts; numeric position does not prove homing."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class HomingEvidence:
    generation: int | None = None
    requested_at: float | None = None
    axes: tuple[bool, bool, bool] | None = None
    received_at: float | None = None

    def invalidate(self) -> None:
        self.generation = None
        self.requested_at = None
        self.axes = None
        self.received_at = None

    def request(self, generation: int, now: float) -> bool:
        if self.generation == generation and self.requested_at is not None:
            if 0 <= now - self.requested_at <= 3:
                return False
            self.invalidate()
        if self.generation != generation:
            self.axes = None
            self.received_at = None
        self.generation = generation
        self.requested_at = now
        return True

    def observe(self, text: str, generation: int, now: float) -> bool:
        if self.generation != generation or self.requested_at is None:
            return False
        if not 0 <= now - self.requested_at <= 3:
            self.invalidate()
            return False
        match = re.fullmatch(r"X:([01])\s+Y:([01])\s+Z:([01])(?:\s+A:[01])?\s*", text)
        if match is None:
            self.invalidate()
            return False
        self.axes = tuple(value == "1" for value in match.groups()[:3])
        self.received_at = now
        self.requested_at = None
        return True

    def homed(self, generation: int, now: float | None = None) -> bool | None:
        if now is not None and (self.received_at is None or not 0 <= now - self.received_at <= 3):
            return None
        return all(self.axes) if self.generation == generation and self.axes is not None else None
