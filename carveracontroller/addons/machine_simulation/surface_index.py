"""Conservative ray candidates for validated immutable indexed geometry."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

Vec3 = tuple[float, float, float]
Bounds = tuple[Vec3, Vec3]


def ray_may_hit(bounds: Bounds, origin: Sequence[float], direction: Sequence[float], limit: float) -> bool:
    near, far = 0.0, limit
    for axis in range(3):
        low, high = bounds[0][axis], bounds[1][axis]
        point, step = origin[axis], direction[axis]
        if not math.isfinite(point):
            return True
        margin = 4e-9 * max(1.0, abs(low), abs(high), abs(point), high - low)
        low, high = low - margin, high + margin
        if not all(math.isfinite(value) for value in (low, high)):
            return True
        if step == 0:
            if point < low or point > high:
                return False
            continue
        entry, exit_distance = (low - point) / step, (high - point) / step
        if not all(math.isfinite(value) for value in (entry, exit_distance)):
            return True
        near = max(near, min(entry, exit_distance))
        far = min(far, max(entry, exit_distance))
        if near > far:
            return False
    return True


@dataclass(frozen=True)
class SurfaceNode:
    bounds: Bounds
    triangles: tuple[int, ...] = ()
    children: tuple[SurfaceNode, ...] = ()

    def candidates(self, origin: Sequence[float], direction: Sequence[float], limit: float) -> tuple[int, ...]:
        pending = [self]
        result = []
        while pending:
            node = pending.pop()
            if not ray_may_hit(node.bounds, origin, direction, limit):
                continue
            result.extend(node.triangles)
            pending.extend(node.children)
        # Preserve exact scan order and original triangle identities, including ties.
        return tuple(sorted(result))


def build_surface_index(vertices: Sequence[float], indices: Sequence[int]) -> SurfaceNode:
    """Caller owns index/position validation; tree contains only derived bounds."""
    # CAD triangles already arrive in local face order. Index compact leaves
    # rather than repeatedly sorting and boxing every individual triangle.
    leaf_indices = 96  # 32 triangles; exact tests still decide every candidate.
    boxes: list[Bounds] = []
    for start in range(0, len(indices), leaf_indices):
        ids = indices[start : start + leaf_indices]
        axes = [[vertices[i * 10 + a] for i in ids] for a in range(3)]
        low = [min(values) for values in axes]
        high = [max(values) for values in axes]
        boxes.append(((low[0], low[1], low[2]), (high[0], high[1], high[2])))

    def branch(ids: list[int]) -> SurfaceNode:
        low = [min(boxes[i][0][a] for i in ids) for a in range(3)]
        high = [max(boxes[i][1][a] for i in ids) for a in range(3)]
        bounds: Bounds = ((low[0], low[1], low[2]), (high[0], high[1], high[2]))
        if len(ids) == 1:
            start = ids[0] * leaf_indices
            return SurfaceNode(bounds, tuple(range(start, min(len(indices), start + leaf_indices), 3)))
        axis = max(range(3), key=lambda a: bounds[1][a] - bounds[0][a])
        ordered = sorted(ids, key=lambda i: boxes[i][0][axis] / 2 + boxes[i][1][axis] / 2)
        middle = len(ordered) // 2
        return SurfaceNode(bounds, children=(branch(ordered[:middle]), branch(ordered[middle:])))

    return branch(list(range(len(boxes))))
