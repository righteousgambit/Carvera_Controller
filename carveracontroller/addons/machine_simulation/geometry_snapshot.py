"""Immutable indexed CAD snapshots with once-validated exact position bounds."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite


def indexed_bounds(values, indices):
    """Bounds of indexed vertices; editable geometry is validated on every call."""
    if not indices:
        return None
    if len(values) % 10:
        raise ValueError("Invalid scene vertex stride")
    count = len(values) // 10
    low, high = [float("inf")] * 3, [float("-inf")] * 3
    for index in set(indices):
        if type(index) is not int or not 0 <= index < count:
            raise ValueError("Invalid scene vertex index")
        point = values[index * 10 : index * 10 + 3]
        if any(not isfinite(v) for v in point):
            raise ValueError("Nonfinite scene geometry")
        for axis, value in enumerate(point):
            low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
    return tuple(low), tuple(high)


@dataclass(frozen=True)
class GeometrySnapshot:
    vertices: tuple
    indices: tuple
    bounds: tuple | None = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "vertices", tuple(self.vertices))
        object.__setattr__(self, "indices", tuple(self.indices))
        object.__setattr__(self, "bounds", indexed_bounds(self.vertices, self.indices))
