"""Immutable indexed CAD snapshots with once-validated exact position bounds."""

from __future__ import annotations

import threading
from _thread import LockType
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import TypeVar

from .surface_index import SurfaceNode, build_surface_index

T = TypeVar("T")


Vec3 = tuple[float, float, float]
Bounds = tuple[Vec3, Vec3]
RenderBatch = tuple[tuple[float, ...], tuple[int, ...]]
RenderBatches = tuple[RenderBatch, ...]
RenderFrame = tuple[tuple[float, ...], float, int]


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise InterruptedError("Geometry snapshot preparation cancelled")


def _snapshot_tuple(values: Sequence[T], cancelled: Callable[[], bool] | None) -> tuple[T, ...]:
    if cancelled is None:
        return tuple(values)
    # Immutable tuples need no copy. Other sequences are copied in bounded
    # chunks so Cancel is observed before the complete snapshot is published.
    _check_cancelled(cancelled)
    if type(values) is tuple:
        return tuple(values)
    result = []
    for start in range(0, len(values), 1280):
        _check_cancelled(cancelled)
        result.extend(values[start : start + 1280])
    _check_cancelled(cancelled)
    return tuple(result)


def indexed_bounds(
    values: Sequence[float], indices: Sequence[int], *, cancelled: Callable[[], bool] | None = None
) -> Bounds | None:
    """Bounds of indexed vertices; editable geometry is validated on every call."""
    _check_cancelled(cancelled)
    if not indices:
        return None
    if len(values) % 10:
        raise ValueError("Invalid scene vertex stride")
    count = len(values) // 10
    low, high = [float("inf")] * 3, [float("-inf")] * 3
    seen: set[int] = set()
    for position, index in enumerate(indices):
        if position % 128 == 0:
            _check_cancelled(cancelled)
        if type(index) is not int or not 0 <= index < count:
            raise ValueError("Invalid scene vertex index")
        if index in seen:
            continue
        seen.add(index)
        point = values[index * 10 : index * 10 + 3]
        if any(type(v) not in (int, float) or not isfinite(v) for v in point):
            raise ValueError("Nonfinite scene geometry")
        for axis, value in enumerate(point):
            low[axis], high[axis] = min(low[axis], value), max(high[axis], value)
    _check_cancelled(cancelled)
    return (low[0], low[1], low[2]), (high[0], high[1], high[2])


@dataclass(frozen=True, init=False)
class GeometrySnapshot:
    vertices: tuple[float, ...]
    indices: tuple[int, ...]
    bounds: Bounds | None = field(init=False)
    _surface_index: SurfaceNode | None = field(default=None, init=False, repr=False, compare=False)
    _render_lock: LockType = field(init=False, repr=False, compare=False)

    _render_frames: OrderedDict[RenderFrame, RenderBatches] = field(init=False, repr=False, compare=False)

    def __init__(
        self, vertices: Sequence[float], indices: Sequence[int], *, cancelled: Callable[[], bool] | None = None
    ) -> None:
        object.__setattr__(self, "vertices", _snapshot_tuple(vertices, cancelled))
        object.__setattr__(self, "indices", _snapshot_tuple(indices, cancelled))
        object.__setattr__(self, "_surface_index", None)
        object.__setattr__(self, "bounds", indexed_bounds(self.vertices, self.indices, cancelled=cancelled))
        object.__setattr__(self, "_render_lock", threading.Lock())
        object.__setattr__(self, "_render_frames", OrderedDict())

    def __deepcopy__(self, memo: dict[int, object]) -> GeometrySnapshot:
        # Geometry is immutable; the private derived cache is not scene data.
        memo[id(self)] = self
        return self

    def __reduce__(self) -> tuple[type[GeometrySnapshot], tuple[tuple[float, ...], tuple[int, ...]]]:
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

    def surface_candidates(
        self, origin: Sequence[float], direction: Sequence[float], limit: float
    ) -> range | tuple[int, ...]:
        index = self.prepare_surface_index()
        return range(0, len(self.indices), 3) if index is None else index.candidates(origin, direction, limit)

    def render_batches(
        self, work_offset_mm: Sequence[float], scale: float = 1.0, max_vertices: int = 65535
    ) -> RenderBatches:
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

    def _prepare_render_batches(self, offset: Sequence[float], scale: float, max_vertices: int) -> RenderBatches:
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
