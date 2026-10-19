"""Prepare the legacy preview parser without publishing controller or GUI state."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from carveracontroller.CNC import CNC

MAX_PREVIEW_POINTS = 2_000_000


@dataclass(frozen=True)
class PreviewParserInputs:
    clearance_z: float
    wcoz: float
    inch: bool
    accuracy: float

    def __post_init__(self) -> None:
        if any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in (self.clearance_z, self.wcoz, self.accuracy)
        ):
            raise ValueError("Preview parser values must be finite numbers")
        if type(self.inch) is not bool or self.accuracy <= 0:
            raise ValueError("Preview parser units and positive arc resolution are required")

    @staticmethod
    def declarations(variables: Mapping[str, Any], *, inch: bool, accuracy: float) -> dict[str, Any]:
        """Retain raw cached inputs; validation belongs on the preparation worker."""
        return {
            "clearance_z": variables.get("clearance_z", -3.0),
            "wcoz": variables.get("wcoz", 0.0),
            "inch": inch,
            "accuracy": accuracy,
        }


def validate_preview_program(
    lines: Sequence[str],
    inputs: PreviewParserInputs,
    *,
    point_budget: int = MAX_PREVIEW_POINTS,
    cancelled: Callable[[], bool] = lambda: False,
) -> int:
    """Exercise exact legacy parsing; no source read, global-state update or partial result."""
    parser = CNC(
        variables={"clearance_z": inputs.clearance_z, "wcoz": inputs.wcoz},
        point_budget=point_budget,
        cancelled=cancelled,
    )
    parser.inch, parser.accuracy = inputs.inch, inputs.accuracy
    count = 0
    for number, line in enumerate(lines, 1):
        if cancelled():
            raise InterruptedError("Preview parsing cancelled")
        if not isinstance(line, str):
            raise ValueError("Preview program lines must be text")
        try:
            parser.parseLine(line, number)
        except InterruptedError:
            raise
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise ValueError(f"Program preview failed at line {number}: {exc}") from exc
        for row in parser.coordinates:
            if any(not math.isfinite(value) for value in row):
                raise ValueError(f"Program preview has nonfinite coordinates at line {number}")
        count += len(parser.coordinates)
        parser.coordinates = []
    if cancelled():
        raise InterruptedError("Preview parsing cancelled")
    return count
