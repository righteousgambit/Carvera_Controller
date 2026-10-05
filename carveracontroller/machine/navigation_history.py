"""Bounded session navigation; candidates commit only after successful restoration."""

from __future__ import annotations

from copy import deepcopy
from typing import Generic, TypeVar

Point = TypeVar("Point")


class NavigationHistory(Generic[Point]):
    def __init__(self, limit: int = 100) -> None:
        if type(limit) is not int or not 2 <= limit <= 1000:
            raise ValueError("History limit must be 2..1000")
        self.limit = limit
        self.items: list[Point] = []
        self.index = -1

    def clear(self) -> None:
        self.items.clear()
        self.index = -1

    @property
    def can_back(self) -> bool:
        return self.index > 0

    @property
    def can_forward(self) -> bool:
        return 0 <= self.index < len(self.items) - 1

    def record(self, point: Point) -> None:
        point = deepcopy(point)
        if self.index >= 0 and self.items[self.index] == point:
            return
        del self.items[self.index + 1 :]
        self.items.append(point)
        if len(self.items) > self.limit:
            del self.items[: len(self.items) - self.limit]
        self.index = len(self.items) - 1

    def update_current(self, point: Point) -> None:
        if self.index >= 0:
            self.items[self.index] = deepcopy(point)

    def candidate(self, direction: int) -> tuple[int, Point] | None:
        if direction not in (-1, 1) or type(direction) is not int:
            raise ValueError("History direction must be -1 or 1")
        index = self.index + direction
        if not 0 <= index < len(self.items):
            return None
        return index, deepcopy(self.items[index])

    def commit(self, index: int) -> None:
        if type(index) is not int or not 0 <= index < len(self.items) or abs(index - self.index) != 1:
            raise ValueError("History candidate is no longer adjacent")
        self.index = index
