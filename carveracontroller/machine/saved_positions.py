"""Named machine positions.

Chip clearing, tool changing and inspection all mean moving somewhere
specific, and typing the same coordinates repeatedly is how a wrong one gets
typed. Positions are stored in machine coordinates so they survive a change
of work origin, which is the whole point of having them.

Kivy-free by contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

POSITIONS_FORMAT_VERSION = 1


@dataclass(frozen=True)
class SavedPosition:
    name: str
    x: float | None = None
    y: float | None = None
    z: float | None = None
    a: float | None = None
    note: str = ""

    @property
    def is_empty(self) -> bool:
        return all(v is None for v in (self.x, self.y, self.z, self.a))

    def to_gcode(self, safe_z_first: bool = True) -> list[str]:
        """Moves that go here, in machine coordinates.

        Z retracts before any XY move by default. Travelling to a saved
        position while still down in a part is how fixtures get destroyed,
        and a preset that does it is worse than no preset.
        """
        if self.is_empty:
            return []

        lines: list[str] = []
        if safe_z_first and (self.x is not None or self.y is not None):
            lines.append("G53 G0 Z-5.000")

        axes = " ".join(
            f"{letter}{value:.3f}"
            for letter, value in (("X", self.x), ("Y", self.y), ("A", self.a))
            if value is not None
        )
        if axes:
            lines.append(f"G53 G0 {axes}")
        if self.z is not None:
            lines.append(f"G53 G0 Z{self.z:.3f}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "x": self.x, "y": self.y, "z": self.z, "a": self.a, "note": self.note}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> SavedPosition:
        def axis(key: str) -> float | None:
            value = data.get(key)
            return None if value is None else float(value)

        return SavedPosition(
            name=str(data["name"]),
            x=axis("x"),
            y=axis("y"),
            z=axis("z"),
            a=axis("a"),
            note=str(data.get("note", "")),
        )


class SavedPositions:
    def __init__(self, positions: list[SavedPosition] | None = None) -> None:
        self._positions: dict[str, SavedPosition] = {p.name: p for p in (positions or [])}

    def save(self, position: SavedPosition) -> None:
        self._positions[position.name] = position

    def remove(self, name: str) -> None:
        self._positions.pop(name, None)

    def get(self, name: str) -> SavedPosition | None:
        return self._positions.get(name)

    def names(self) -> list[str]:
        return sorted(self._positions)

    def to_json(self) -> str:
        return json.dumps(
            {
                "version": POSITIONS_FORMAT_VERSION,
                "positions": [self._positions[n].to_dict() for n in self.names()],
            },
            indent=2,
        )

    @staticmethod
    def from_json(text: str) -> SavedPositions:
        if not text.strip():
            return SavedPositions()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return SavedPositions()
            entries = data.get("positions", [])
            if not isinstance(entries, list):
                return SavedPositions()
            return SavedPositions([SavedPosition.from_dict(p) for p in entries])
        except (ValueError, KeyError, TypeError, AttributeError):
            return SavedPositions()
