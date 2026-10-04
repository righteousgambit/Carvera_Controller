"""Declared dimensions for an inspection drawing; no seating defaults or offsets."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Dimension:
    name: str
    start: float | None
    end: float | None

    @property
    def value(self):
        return None if self.start is None or self.end is None else self.end - self.start

    @property
    def caption(self):
        return f"{self.name}: unknown" if self.value is None else f"{self.name}: {self.value:g} mm"


def assembly_dimensions(definition):
    """Canonical-mm inputs. Insertion is derived only from declared compatible lengths."""
    for key in ("length", "stickout", "flute_length", "diameter", "shank_diameter"):
        value = getattr(definition, key)
        if value is not None and (isinstance(value, bool) or not math.isfinite(value) or value <= 0):
            raise ValueError(f"{key} must be a positive finite dimension")
    overall, stickout, flute = definition.length, definition.stickout, definition.flute_length
    if overall is not None and stickout is not None and stickout > overall:
        raise ValueError("Stickout exceeds overall cutter length")
    if flute is not None and stickout is not None and flute > stickout:
        raise ValueError("Cutting length exceeds declared stickout")
    if flute is not None and overall is not None and flute > overall:
        raise ValueError("Cutting length exceeds overall cutter length")
    return (
        Dimension("Overall", 0, overall),
        Dimension("Cutting length", 0, flute),
        Dimension("Stickout", 0, stickout),
        Dimension("Inserted cutter", stickout, overall),
    )
