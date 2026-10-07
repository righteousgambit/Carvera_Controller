"""Immutable indexed CAD snapshots with once-validated exact position bounds."""

from __future__ import annotations

import threading
from _thread import LockType
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite

from .surface_index import SurfaceNode, build_surface_index

Vec3 = tuple[float, float, float]
Bounds = tuple[Vec3, Vec3]


def indexed_bounds(values: Sequence[float], indices: Sequence[int]) -> Bounds | None:
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
        if any(type(v) not in (int, float) or not isfinite(v) for v in point):
            raise ValueError("Nonfinite scene geometry")
        for axis, value in enumerate(point):
            low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
    return (low[0], low[1], low[2]), (high[0], high[1], high[2])


@dataclass(frozen=True)
class GeometrySnapshot:
    vertices: tuple[float, ...]
    indices: tuple[int, ...]
    bounds: Bounds | None = field(init=False)
    _surface_index: SurfaceNode | None = field(default=None, init=False, repr=False, compare=False)
    _render_lock: LockType = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "vertices", tuple(self.vertices))
        object.__setattr__(self, "indices", tuple(self.indices))
        object.__setattr__(self, "bounds", indexed_bounds(self.vertices, self.indices))
        object.__setattr__(self, "_render_lock", threading.Lock())
        object.__setattr__(self, "_render_frames", OrderedDict())

    def __deepcopy__(self, memo):
        # Geometry is immutable; the private derived cache is not scene data.
        memo[id(self)] = self
        return self

    def __reduce__(self):
        return type(self), (self.vertices, self.indices)

    def prepare_surface_index(self) -> SurfaceNode | None:
        """Warm on the CAD worker; retain one derived index for immutable bytes."""
        if len(self.indices) % 3:
            raise ValueError("Surface picking requires complete triangles")
        if len(self.indices) < 384:
            return None
        if self._surface_index is not None:
            return self._surface_index
        prepared = build_surface_index(self.vertices, self.indices)
        with self._render_lock:
            if self._surface_index is None:
                object.__setattr__(self, "_surface_index", prepared)
            return self._surface_index

    def surface_candidates(self, origin, direction, limit):
        index = self.prepare_surface_index()
        return range(0, len(self.indices), 3) if index is None else index.candidates(origin, direction, limit)

    def render_batches(self, work_offset_mm, scale=1.0, max_vertices=65535):
        """Prepare immutable triangle buffers; retain at most two exact frames.

        Workers can warm these before publication. Main-thread cache hits do
        not wait for a different frame's conversion. GPU instructions remain
        exclusively owned by the UI thread.
        """
        offset = tuple(float(v) for v in work_offset_mm)
        scale = float(scale)
        if len(offset) != 3 or not all(isfinite(v) for v in offset) or not isfinite(scale) or scale <= 0:
            raise ValueError("Render frame requires finite XYZ and positive scale")
        if type(max_vertices) is not int or not 3 <= max_vertices <= 65535 or len(self.indices) % 3:
            raise ValueError("Render buffers require triangles and unsigned-short batch limits")
        max_vertices -= max_vertices % 3
        key = (offset, scale, max_vertices)
        with self._render_lock:
            cached = self._render_frames.get(key)
            if cached is not None:
                self._render_frames.move_to_end(key)
                return cached
        result = self._prepare_render_batches(offset, scale, max_vertices)
        with self._render_lock:
            cached = self._render_frames.get(key)
            if cached is not None:
                return cached
            self._render_frames[key] = result
            while len(self._render_frames) > 2:
                self._render_frames.popitem(last=False)
        return result

    def _prepare_render_batches(self, offset, scale, max_vertices):
        batches = []
        for start in range(0, len(self.indices), max_vertices):
            indices = self.indices[start : start + max_vertices]
            vertices = []
            for index in indices:
                position = index * 10
                point = tuple((float(self.vertices[position + axis]) - offset[axis]) * scale for axis in range(3))
                if not all(isfinite(v) for v in point):
                    raise ValueError("Render frame overflows finite coordinates")
                vertices.extend(point)
                vertices.extend(self.vertices[position + 3 : position + 10])
            batches.append((tuple(vertices), tuple(range(len(indices)))))
        return tuple(batches)
